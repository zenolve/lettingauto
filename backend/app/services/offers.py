"""Offer lifecycle service (Gap 5 / Gap 4).

One ``Offers`` row = one tenant offer (joint applicants share a row). The
offer is the lifecycle wrapper around ``Properties.Tenant``:

- ``Properties.Tenant`` is set **only when an offer is accepted** â€” so multiple
  competing Pending offers can coexist on a property without clobbering each
  other (the old behaviour overwrote the link on every new offer).
- Accepting one offer supersedes the other Pending offers on that property.
- Rejecting/withdrawing the *accepted* offer rolls ``Properties.Tenant`` +
  ``LL_Offer_Accepted`` back so the property returns to the offer stage.

Used by both the manual endpoints (``routers/offers.py``) and the DocuSign
offer-letter webhook (``pg04_docuseal``) via the same functions.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.core.logger import get_logger
from app.db import supabase_client as at

logger = get_logger(__name__)

# Terminal statuses that close an offer (vs. the live "Pending"/"Accepted").
CLOSED_STATUSES = {
    "Rejected_By_Landlord",
    "Withdrawn_By_Tenant",
    "Expired",
    "Failed_Referencing",
    "Superseded",
}


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def offers_for_property(property_id: str) -> list[dict]:
    """Return every Offer row linked to a property, newest first."""
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        return []
    offer_ids = prop.get("fields", {}).get("Offers") or []
    out: list[dict] = []
    for oid in offer_ids:
        try:
            out.append(at.get(at.TableNames.OFFERS, oid))
        except Exception:
            continue
    out.sort(key=lambda r: r.get("fields", {}).get("Created At") or "", reverse=True)
    return out


def find_offer_by_envelope(envelope_id: str | None) -> dict | None:
    if not envelope_id:
        return None
    return at.find_first(at.TableNames.OFFERS, at.eq("DocuSign Envelope ID", envelope_id))


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def create_offer(
    *,
    property_id: str,
    tenant_ids: list[str],
    lead_tenant_name: str,
    monthly_rent: float,
    rent_frequency: str,
    deposit_amount: float,
    holding_deposit: float,
    start_date: str,
    end_date: str | None,
    tenancy_term: str | None,
    holding_deposit_deadline: str | None,
    envelope_id: str | None,
    agent_email: str | None,
) -> str:
    """Create a Pending Offer row. Does NOT touch Properties.Tenant."""
    try:
        addr = at.get(at.TableNames.PROPERTIES, property_id).get("fields", {}).get("Address", "")
    except Exception:
        addr = ""
    fields: dict[str, Any] = {
        "Name": (f"Offer · {lead_tenant_name} · {addr}").strip(" ·") or "Offer",
        "Property": [property_id],
        "Tenants": tenant_ids,
        "Status": "Pending",
        "Offered Rent": monthly_rent,
        "Rent Frequency": rent_frequency,
        "Deposit": deposit_amount,
        "Holding Deposit": holding_deposit,
        "Start Date": start_date,
        "End Date": end_date,
        "Tenancy Term": tenancy_term,
        "Holding Deposit Deadline": holding_deposit_deadline,
        "DocuSign Envelope ID": envelope_id,
        "Created At": date.today().isoformat(),
        "Created By": agent_email,
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    rec = at.create(at.TableNames.OFFERS, fields)
    logger.info("offers.created id=%s property=%s tenants=%d", rec["id"], property_id, len(tenant_ids))
    return rec["id"]


# ---------------------------------------------------------------------------
# Accept
# ---------------------------------------------------------------------------
async def accept_offer(offer_id: str, *, source: str = "manual") -> dict[str, Any]:
    """Accept an offer: link its tenants to the property, flip
    LL_Offer_Accepted, supersede other Pending offers, advance the gate."""
    offer = at.get(at.TableNames.OFFERS, offer_id)
    of = offer.get("fields", {})
    prop_ids = of.get("Property") or []
    tenant_ids = of.get("Tenants") or []
    if not prop_ids:
        raise ValueError(f"Offer {offer_id} has no linked property")
    property_id = prop_ids[0]

    at.update(at.TableNames.PROPERTIES, property_id, {
        "Tenant": tenant_ids,
        "LL_Offer_Accepted": True,
    })
    at.update(at.TableNames.OFFERS, offer_id, {
        "Status": "Accepted",
        "Closed At": date.today().isoformat(),
    })
    _supersede_other_pending(property_id, keep_offer_id=offer_id)

    from app.handlers.pg00_gate import evaluate_gate  # local â€” avoid load cycle
    gate = await evaluate_gate(property_id, target_stage=5, source=f"Offer accepted ({source})")
    logger.info("offers.accepted id=%s property=%s source=%s", offer_id, property_id, source)
    return {"offer_id": offer_id, "property_id": property_id, "status": "Accepted", "gate": gate.to_dict()}


def _supersede_other_pending(property_id: str, *, keep_offer_id: str) -> None:
    for o in offers_for_property(property_id):
        if o["id"] == keep_offer_id:
            continue
        if o.get("fields", {}).get("Status") == "Pending":
            try:
                at.update(at.TableNames.OFFERS, o["id"], {
                    "Status": "Superseded",
                    "Closed At": date.today().isoformat(),
                    "Close Reason": "Another offer on this property was accepted.",
                })
            except Exception as e:  # noqa: BLE001
                logger.warning("offers.supersede_failed id=%s err=%s", o["id"], e)


# ---------------------------------------------------------------------------
# Close (reject / withdraw / expire / fail)
# ---------------------------------------------------------------------------
async def close_offer(
    offer_id: str,
    *,
    status: str,
    reason: str | None = None,
    void_envelope: bool = True,
    source: str = "manual",
) -> dict[str, Any]:
    """Move an offer to a terminal status. If it was the *accepted* offer,
    roll back Properties.Tenant + LL_Offer_Accepted so the property returns to
    the offer stage. Best-effort voids the DocuSign envelope."""
    if status not in CLOSED_STATUSES:
        raise ValueError(f"close_offer: {status!r} is not a terminal status")

    offer = at.get(at.TableNames.OFFERS, offer_id)
    of = offer.get("fields", {})
    prop_ids = of.get("Property") or []
    property_id = prop_ids[0] if prop_ids else None
    was_accepted = of.get("Status") == "Accepted"

    update: dict[str, Any] = {"Status": status, "Closed At": date.today().isoformat()}
    if reason:
        update["Close Reason"] = reason
    at.update(at.TableNames.OFFERS, offer_id, update)

    env_id = of.get("DocuSign Envelope ID")
    if void_envelope and env_id:
        try:
            from app.core.docusign_client import void_envelope as _void  # local
            await _void(env_id, reason or f"Offer {status}")
        except Exception as e:  # noqa: BLE001 â€” completed/declined envelopes can't be voided
            logger.warning("offers.void_envelope_failed id=%s err=%s", env_id, e)

    rolled_back = False
    if property_id and was_accepted:
        prop = at.get(at.TableNames.PROPERTIES, property_id).get("fields", {})
        cur = set(prop.get("Tenant") or [])
        mine = set(of.get("Tenants") or [])
        # Only roll back if the property's current tenant link is this offer's.
        if cur and cur == mine:
            at.update(at.TableNames.PROPERTIES, property_id, {
                "Tenant": [],
                "LL_Offer_Accepted": False,
                "Gate Status": "Clear",
                "Gate Block Reason": "",
            })
            rolled_back = True

    logger.info("offers.closed id=%s status=%s rolled_back=%s source=%s",
                offer_id, status, rolled_back, source)
    return {
        "offer_id": offer_id,
        "property_id": property_id,
        "status": status,
        "rolled_back_property": rolled_back,
    }
