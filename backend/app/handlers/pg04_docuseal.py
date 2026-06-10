"""PG_04 â€” DocuSeal webhook handler (spec Â§6.5)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.core.email_client import send_agent_summary
from app.core.logger import get_logger
from app.db import supabase_client as at
from app.handlers.pg00_gate import evaluate_gate, find_stage_agent_email
from app.services.derivations import parse_iso_date

logger = get_logger(__name__)


def _doc_kind(template_name: str, library_doc_id: str | None = None) -> str:
    """Map a DocuSeal template name (or library doc id) to a logical document kind.

    DocuSign Connect can omit ``emailSubject`` from the webhook payload if the
    Connect configuration doesn't tick "Include Envelope Data" â€” in that case
    the normaliser falls back to the library doc id (e.g. ``pg_tcs_2026``).
    We classify off that too so the gate routing still works.
    """
    n = (template_name or "").lower()
    if "terms" in n or "t&c" in n or "t & c" in n:
        return "TC"
    if "tenancy agreement" in n or "assured" in n or n.endswith(" ta"):
        return "TA"
    if "offer" in n:
        return "OFFER"

    # Fallback to the library doc id when the template name is unhelpful.
    lid = (library_doc_id or "").lower()
    if "tcs" in lid or lid.startswith("pg_tcs") or lid.startswith("pg_terms"):
        return "TC"
    if lid in {"apt_pet_abnb", "common_law_ta", "ta_common_law"} or "ta_" in lid or "_ta" in lid:
        return "TA"
    if "offer" in lid:
        return "OFFER"
    return "OTHER"


def _find_property(metadata: dict[str, Any] | None) -> dict | None:
    if metadata and metadata.get("property_id"):
        try:
            return at.get(at.TableNames.PROPERTIES, metadata["property_id"])
        except Exception:
            return None
    return None


async def handle_docuseal_event(payload: dict[str, Any]) -> dict:
    event = payload.get("event") or payload.get("event_type") or ""
    data = payload.get("data") or {}
    template = data.get("template") or {}
    template_name = template.get("name", "")
    submitters = data.get("submitters") or []
    metadata = data.get("metadata") or {}
    kind = _doc_kind(template_name, metadata.get("library_doc"))

    prop = _find_property(metadata)
    if not prop:
        logger.warning("docuseal.event property not found template=%r", template_name)
        return {"ignored": True, "reason": "property_not_found"}
    property_id = prop["id"]
    pfields = prop.get("fields", {})

    declined = "declin" in event.lower()
    completed = "complet" in event.lower() or "sign" in event.lower()

    if declined:
        at.update(at.TableNames.PROPERTIES, property_id, {
            "Gate Status": "Blocked",
            "Gate Block Reason": f"Document declined: {template_name}",
        })
        # Reflect the decline on the Sent_Documents row (if one exists).
        try:
            from app.services.sent_documents import update_status_by_envelope  # noqa: PLC0415
            update_status_by_envelope(data.get("submission_id") or data.get("id"),
                                      "Declined", completed=True)
        except Exception:  # noqa: BLE001
            pass
        decline_warning = f"{template_name} was declined by signer."
        try:
            from app.handlers.pg00_gate import _log_gate  # local import â€” avoid load-time cycle
            await _log_gate(
                property_id,
                int(pfields.get("Stage_Order", 4) or 4),
                passed=False,
                reasons=[f"Document declined: {template_name}"],
                warnings=[decline_warning],
                source=f"PG_04 DocuSeal decline ({kind})",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("docuseal.decline.log_failed err=%s", e)
        # Gap 5: a declined OFFER letter closes the matching Offer row.
        if kind == "OFFER":
            try:
                from app.services.offers import find_offer_by_envelope, close_offer  # noqa: PLC0415
                env_id = data.get("submission_id") or data.get("id")
                offer = find_offer_by_envelope(env_id)
                if offer:
                    await close_offer(
                        offer["id"], status="Rejected_By_Landlord",
                        reason="Landlord declined the offer letter.",
                        void_envelope=False,  # a declined envelope can't be voided
                        source="docusign",
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("docuseal.offer_decline_close_failed err=%s", e)
        await send_agent_summary(
            find_stage_agent_email(pfields.get("Stage_Order", 4)) or "",
            subject=f"Document DECLINED â€” {template_name}",
            template="E08_document_declined.html",
            context={
                "property_address": pfields.get("Address"),
                "doc_title": template_name,
                "warnings": [decline_warning],
            },
        )
        return {"declined": True, "property_id": property_id}

    if not completed:
        return {"ignored": True, "event": event}

    # Reflect the completion on the Sent_Documents row (covers TC / TA / OFFER;
    # runs before the OFFER early-return below).
    try:
        from app.services.sent_documents import update_status_by_envelope  # noqa: PLC0415
        update_status_by_envelope(data.get("submission_id") or data.get("id"),
                                  "Signed", completed=True)
    except Exception:  # noqa: BLE001
        pass

    # Gap 5: an OFFER-letter completion is the landlord accepting that offer.
    # Route it through the offers service so the right Offer row is Accepted,
    # its tenants are linked to the property, and rival Pending offers are
    # superseded. Falls back to the legacy LL_Offer_Accepted flag if no Offer
    # row exists (pre-Gap-5 data).
    if kind == "OFFER":
        try:
            from app.services.offers import (  # noqa: PLC0415
                accept_offer, find_offer_by_envelope, offers_for_property,
            )
            env_id = data.get("submission_id") or data.get("id")
            offer = find_offer_by_envelope(env_id)
            if not offer:
                pend = [o for o in offers_for_property(property_id)
                        if o.get("fields", {}).get("Status") == "Pending"]
                offer = pend[0] if pend else None
            if offer:
                res = await accept_offer(offer["id"], source="docusign")
                await send_agent_summary(
                    find_stage_agent_email(4) or "",
                    subject=f"Offer accepted â€” {template_name}",
                    template="E07_document_signed.html",
                    context={
                        "property_address": pfields.get("Address"),
                        "doc_title": template_name, "kind": kind, "submitters": submitters,
                    },
                )
                return {"property_id": property_id, "kind": kind,
                        "offer_accepted": offer["id"], "gate": res.get("gate")}
        except Exception as e:  # noqa: BLE001
            logger.warning("docuseal.offer_accept_failed err=%s â€” falling back", e)
        # fall through to legacy flag-set below if no offer row / on error

    update: dict[str, Any] = {}

    if kind == "TC":
        update["TC_Signed"] = True
        # Mirror on the linked landlords
        for lid in pfields.get("Landlords", []) or []:
            try:
                at.update(at.TableNames.LANDLORDS, lid, {"TC_Signed": True})
            except Exception:
                pass

    elif kind == "TA":
        for s in submitters:
            email = (s.get("email") or "").lower()
            # Try to match landlord first
            ll = at.find_first(at.TableNames.LANDLORDS, at.eq("Email Address", email))
            if ll:
                update["TA_LL_Signed"] = True
                try:
                    at.update(at.TableNames.LANDLORDS, ll["id"], {"TA_Signed": True})
                except Exception:
                    pass
                continue
            tt = at.find_first(at.TableNames.TENANTS, at.eq("Tenant Email", email))
            if tt:
                # Per-tenant signature. On a joint tenancy EVERY named tenant
                # must sign before the tenant side of the TA is complete â€” a
                # single signer no longer advances the property.
                try:
                    at.update(at.TableNames.TENANTS, tt["id"], {"TA_Signed": True})
                except Exception as e:  # noqa: BLE001
                    logger.warning("ta.tenant_sign_mark_failed id=%s err=%s", tt["id"], e)
        # Roll up to the property: TA_TT_Signed becomes True only once *all*
        # linked tenants have TA_Signed. (Manual override still works â€” the
        # PropertyFlags toggle sets TA_TT_Signed directly.)
        tenant_ids = pfields.get("Tenant") or []
        if tenant_ids:
            all_signed = True
            for tid in tenant_ids:
                try:
                    tf = at.get(at.TableNames.TENANTS, tid).get("fields", {})
                except Exception:
                    all_signed = False
                    break
                if not tf.get("TA_Signed"):
                    all_signed = False
                    break
            if all_signed:
                update["TA_TT_Signed"] = True

    elif kind == "OFFER":
        update["LL_Offer_Accepted"] = True

    if update:
        at.update(at.TableNames.PROPERTIES, property_id, update)

    # If TA fully signed, create Financials + diary entries
    if kind == "TA":
        refreshed = at.get(at.TableNames.PROPERTIES, property_id).get("fields", {})
        if refreshed.get("TA_LL_Signed") and refreshed.get("TA_TT_Signed"):
            _create_financials(property_id)
            _create_ta_diary_entries(property_id, refreshed)

    # Email agent
    agent_email = find_stage_agent_email(4)
    await send_agent_summary(
        agent_email or "",
        subject=f"{template_name} signed",
        template="E07_document_signed.html",
        context={
            "property_address": pfields.get("Address"),
            "doc_title": template_name,
            "kind": kind,
            "submitters": submitters,
        },
    )

    # Re-evaluate the right gate. Surface the signing event as a "flag" on
    # the Gate_Log row so the property page can mention it.
    target = 3 if kind == "TC" else (5 if kind == "OFFER" else 7)
    gate = await evaluate_gate(
        property_id, target_stage=target,
        actions=[f"{template_name} signed â€” review any post-signing tasks."],
        source=f"PG_04 DocuSeal ({kind})",
    )

    return {"property_id": property_id, "kind": kind, "gate": gate.to_dict()}


def _create_financials(property_id: str) -> None:
    try:
        at.create(at.TableNames.FINANCIALS, {
            "Property": [property_id],
            "Commission_Rate": 0.12,
            "Disbursement_Status": "Pending",
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("financials.create_failed err=%s", e)


def _create_ta_diary_entries(property_id: str, fields: dict) -> None:
    """Schedule the standard post-TA-signed diary entries.

    For APT (Renters' Rights Act 2025): Section 13 / Form 4A rent-review notice
    must be served 2.5 months before the 12-month anniversary â€” i.e. at
    month 9.5. Missing this means no rent increase is possible and Palace Gate
    could be liable to the landlord (per master doc CRITICAL DEADLINES Â§53/Â§96).
    """
    today = date.today()
    start = parse_iso_date(fields.get("Tenancy Start Date"))
    expiry = parse_iso_date(fields.get("Tenancy Expiry Date"))
    gas_exp = parse_iso_date(fields.get("Gas Certificates Expiry"))
    eicr_exp = parse_iso_date(fields.get("EICR Expiry"))
    is_apt = fields.get("Tenancy Type") == "APT"
    address = fields.get("Address", "")

    if start:
        # Step 53 / 96 â€” high-priority Section 13 rent-review alert at month 9.5.
        alert_date = start + timedelta(days=int(9.5 * 30))
        at.create(at.TableNames.DIARY, {
            "Diary_Type": "Rent Review S13",
            "Property": [property_id],
            "Diary Date": today.isoformat(),
            "Alert_Date": alert_date.isoformat(),
            "Alert_Message": f"Section 13 / Form 4A due (month 9.5) â€” {address}",
            "Fired": False,
        })
    if gas_exp:
        at.create(at.TableNames.DIARY, {
            "Diary_Type": "Gas Cert Renewal",
            "Property": [property_id],
            "Diary Date": today.isoformat(),
            "Alert_Date": (gas_exp - timedelta(days=60)).isoformat(),
            "Alert_Message": f"Gas Safety Certificate renewal due â€” {address}",
            "Fired": False,
        })
    if eicr_exp:
        at.create(at.TableNames.DIARY, {
            "Diary_Type": "EICR Renewal",
            "Property": [property_id],
            "Diary Date": today.isoformat(),
            "Alert_Date": (eicr_exp - timedelta(days=60)).isoformat(),
            "Alert_Message": f"EICR renewal due â€” {address}",
            "Fired": False,
        })
    if is_apt and start:
        at.create(at.TableNames.DIARY, {
            "Diary_Type": "TDS 30-Day Countdown",
            "Property": [property_id],
            "Diary Date": today.isoformat(),
            "Alert_Date": (start + timedelta(days=30)).isoformat(),
            "Alert_Message": f"Register deposit with TDS (30-day deadline) â€” {address}",
            "Fired": False,
        })
    if not is_apt and expiry:
        at.create(at.TableNames.DIARY, {
            "Diary_Type": "Tenancy Expiry Warning",
            "Property": [property_id],
            "Diary Date": today.isoformat(),
            "Alert_Date": (expiry - timedelta(days=60)).isoformat(),
            "Alert_Message": f"Tenancy expiry in 60 days â€” begin renewal discussions â€” {address}",
            "Fired": False,
        })
