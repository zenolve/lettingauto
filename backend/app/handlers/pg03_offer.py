"""PG_03 — Offer handler (spec §6.4).

Creates a Tenant record, applies APT validation, sets HMO flag, generates the
DocuSeal Offer Letter, and emails the agent.
"""
from __future__ import annotations

import json
from datetime import date

from app.config import settings
from app.core.docuseal_client import create_template_submission
from app.core.email_client import send_agent_summary
from app.core.logger import get_logger
from app.core.paragon_client import instruct_paragon
from app.db import airtable_client as at
from app.handlers.pg00_gate import evaluate_gate, find_stage_agent_email
from app.models.common import OfferInput
from app.services.apt import validate_apt, weekly_rent_from_monthly
from app.services.derivations import holding_deposit_deadline

logger = get_logger(__name__)


async def handle_offer(property_id: str, payload: OfferInput) -> dict:
    prop = at.get(at.TableNames.PROPERTIES, property_id)
    pfields = prop.get("fields", {})
    tenancy_type = pfields.get("Tenancy Type", "Common Law")

    # 1. APT validation
    violations: list[str] = []
    if tenancy_type == "APT":
        weekly = weekly_rent_from_monthly(payload.monthly_rent)
        violations = validate_apt(
            holding_deposit=payload.holding_deposit,
            weekly_rent=weekly,
            rent_in_advance_months=payload.rent_in_advance_months,
            end_date=payload.end_date.isoformat() if payload.end_date else None,
        )

    if violations:
        at.update(at.TableNames.PROPERTIES, property_id, {
            "Gate Status": "Blocked",
            "Gate Block Reason": "; ".join(violations),
        })
        # Write a Gate_Log row so the property page's ReviewPanel surfaces
        # the APT violations to the agent — without this the early-return
        # path was silent on the dashboard.
        try:
            from app.handlers.pg00_gate import _log_gate  # noqa: PLC0415
            await _log_gate(
                property_id,
                target_stage=5,
                passed=False,
                reasons=violations,
                warnings=violations,
                source="PG_03 Offer (APT violations)",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("offer.gatelog_failed err=%s", e)

        agent_email = find_stage_agent_email(4)
        await send_agent_summary(
            agent_email or "",
            subject=f"APT violation on offer — {pfields.get('Address')}",
            template="E06_apt_violation.html",
            context={
                "property_address": pfields.get("Address"),
                "violations": violations,
                "warnings": violations,
            },
        )
        return {"violations": violations, "blocked": True}

    # 2. Create tenant — includes Right to Rent fields (steps 35–38, 46).
    tenant_fields = {
        "Name": payload.tenant_full_name,
        "Tenant Email": payload.tenant_email,
        "Tenant Address": payload.tenant_address,
        "Start Date": payload.start_date.isoformat(),
        "End Date": payload.end_date.isoformat() if payload.end_date else None,
        "Tenancy Term": payload.tenancy_term,
        "Amount": payload.monthly_rent,
        "Rent_Frequency": payload.rent_frequency,
        "Deposit Amount": payload.deposit_amount,
        "Holding_Deposit": payload.holding_deposit,
        "Rent_In_Advance_Months": payload.rent_in_advance_months,
        "Break Clause": payload.break_clause,
        "Renew": payload.renewal_terms,
        "Special Condition": payload.special_conditions,
        "Guarantor_Name": payload.guarantor_name,
        "Gurantor Address": payload.guarantor_address,  # spelling from spec
        "Guarantor_Email": payload.guarantor_email,
        "Is_Student": payload.is_student,
        "Referencing_Status": "Pending",
        "Property Id": [property_id],  # live Tenant table's link field name
        # Right to Rent capture
        "RTR_Check_Type":    payload.rtr_check_type,
        "RTR_Check_Date":    payload.rtr_check_date.isoformat() if payload.rtr_check_date else None,
        "RTR_Doc_Reference": payload.rtr_doc_reference,
        "Visa_Expiry_Date":  payload.visa_expiry_date.isoformat() if payload.visa_expiry_date else None,
    }
    tenant_fields = {k: v for k, v in tenant_fields.items() if v is not None}
    tenant_record = at.create(at.TableNames.TENANTS, tenant_fields)
    tenant_id = tenant_record["id"]

    # 2b. Persist Right-to-Rent uploads via Compliance audit rows so they're
    #     easy to discover later in a possession dispute.
    today_iso = date.today().isoformat()
    for doc_type, url in [
        ("Other", payload.tenant_passport_upload),
        ("Other", payload.tenant_visa_upload),
        ("Other", payload.tenant_utility_bill_upload),
    ]:
        if not url:
            continue
        try:
            at.create(at.TableNames.COMPLIANCE, {
                "Document_Type": doc_type,
                "Property": [property_id],
                "Tenant": [tenant_id],
                "Served_Date": today_iso,
                "Served_To": payload.tenant_email,
                "Served_As": "Link",
                "File_URL": url,
                "Confirmed_Sent": False,
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("rtr.compliance_create_failed err=%s", e)

    # 2c. Visa expiry → diary follow-up (step 102).
    if payload.visa_expiry_date:
        try:
            from datetime import timedelta  # noqa: PLC0415
            alert = payload.visa_expiry_date - timedelta(days=60)
            at.create(at.TableNames.DIARY, {
                "Diary_Type": "RTR Followup",
                "Property": [property_id],
                "Diary Date": today_iso,
                "Alert_Date": alert.isoformat(),
                "Alert_Message": f"Right to Rent follow-up: visa expires {payload.visa_expiry_date.isoformat()} for {payload.tenant_full_name}.",
                "Fired": False,
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("rtr.diary_create_failed err=%s", e)

    # 2d. Instruct Paragon referencing (mock unless PARAGON_TOKEN set).
    paragon_ref: str | None = None
    if payload.instruct_paragon:
        try:
            paragon_resp = await instruct_paragon(
                tenant_full_name=payload.tenant_full_name,
                tenant_email=payload.tenant_email,
                property_address=pfields.get("Address", ""),
                monthly_rent=payload.monthly_rent,
                guarantor_required=bool(payload.guarantor_name),
                include_right_to_rent=payload.rtr_check_type != "Paragon",
                metadata={"property_id": property_id, "tenant_id": tenant_id},
            )
            paragon_ref = paragon_resp.get("reference_number")
            if paragon_ref:
                at.update(at.TableNames.TENANTS, tenant_id, {
                    "Referencing_Paragon_Ref": paragon_ref,
                })
        except Exception as e:  # noqa: BLE001
            logger.warning("paragon.instruct_failed err=%s", e)

    # 2e. Co-tenants — create one Tenant record per additional occupant.
    co_tenant_ids: list[str] = []
    for ct in payload.co_tenants:
        ct_fields = {
            "Name": ct.full_name,
            "Tenant Email": ct.email,
            "Tenant Address": ct.address,
            "Start Date": payload.start_date.isoformat(),
            "End Date": payload.end_date.isoformat() if payload.end_date else None,
            "Amount": 0,  # co-tenant rent share tracked elsewhere; main tenant carries the lease rent
            "Is_Student": ct.is_student,
            "Referencing_Status": "Pending",
            "Property Id": [property_id],
            "RTR_Check_Type":    ct.rtr_check_type,
            "RTR_Check_Date":    ct.rtr_check_date.isoformat() if ct.rtr_check_date else None,
            "RTR_Doc_Reference": ct.rtr_doc_reference,
            "Visa_Expiry_Date":  ct.visa_expiry_date.isoformat() if ct.visa_expiry_date else None,
        }
        ct_fields = {k: v for k, v in ct_fields.items() if v is not None}
        try:
            ct_rec = at.create(at.TableNames.TENANTS, ct_fields)
            co_tenant_ids.append(ct_rec["id"])
        except Exception as e:  # noqa: BLE001
            logger.warning("co_tenant.create_failed name=%r err=%s", ct.full_name, e)

    # 3. Link all tenants to the property + HMO flag.
    #    Total occupants = stated count + 1 (lead tenant) + number of co-tenants
    #    if number_of_occupants didn't include them already. We use the max of
    #    the stated count and the actual linked tenant count to be safe.
    total_tenants = max(payload.number_of_occupants, 1 + len(co_tenant_ids))
    all_tenant_ids = [tenant_id] + co_tenant_ids
    hdd_iso = holding_deposit_deadline().isoformat()
    # Gap 5: do NOT set Properties.Tenant here. The tenant link is assigned only
    # when an offer is *accepted* (services/offers.accept_offer), so multiple
    # competing Pending offers no longer clobber each other. We still set the
    # property-level flags derived from the offer (HMO, anti-discrimination,
    # holding-deposit deadline) so the gate/compliance picture stays correct.
    property_update: dict = {
        "Holding_Deposit_Deadline": hdd_iso,
    }
    if total_tenants >= 3:
        property_update["HMO_Flag"] = True
    if payload.anti_discrimination_confirmed:
        property_update["Anti_Discrimination_Confirmed"] = True
        property_update["Anti_Discrimination_Confirmed_Date"] = date.today().isoformat()
    at.update(at.TableNames.PROPERTIES, property_id, property_update)

    # 3b. Offer-chase diary (Gap 2) — the landlord may neither sign nor decline
    #     the offer letter. Nothing else reads Holding_Deposit_Deadline, so the
    #     statutory 15-day holding-deposit clock can quietly run out. Schedule a
    #     chase 7 days out; PG_06 fires it to the stage agent. Uses the existing
    #     "Reminder" Diary_Type (singleSelect has no "Offer Chase" option — a
    #     dedicated type would be a one-option schema add later).
    try:
        from datetime import timedelta  # noqa: PLC0415
        chase_date = (date.today() + timedelta(days=7)).isoformat()
        deadline = hdd_iso
        at.create(at.TableNames.DIARY, {
            "Diary_Type": "Reminder",
            "Property": [property_id],
            "Diary Date": date.today().isoformat(),
            "Alert_Date": chase_date,
            "Alert_Message": (
                f"Offer chase — landlord has not yet signed the offer letter for "
                f"{pfields.get('Address', '')}. Holding-deposit deadline {deadline}. "
                f"Chase or refund before the 15-day limit."
            ),
            "Assigned_To": find_stage_agent_email(4) or settings.admin_email,
            "Fired": False,
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("offer.chase_diary_failed err=%s", e)

    if total_tenants >= 3:
        at.create(at.TableNames.CHECKLIST, {
            "Name": "Confirm HMO licence",
            "Property": [property_id],
            "Status": "Todo",
            "Priority": "Critical",
            "is_gate_item": True,
        })

    # 4. DocuSeal Offer Letter
    docuseal_response: dict = {}
    docuseal_url: str | None = None
    try:
        landlord_id = (pfields.get("Landlords") or [None])[0]
        landlord_email = None
        landlord_name = None
        if landlord_id:
            ll = at.get(at.TableNames.LANDLORDS, landlord_id)
            landlord_email = ll.get("fields", {}).get("Email Address")
            landlord_name = ll.get("fields", {}).get("Full Name")

        if landlord_email:
            docuseal_response = await create_template_submission(
                template_id=settings.docuseal_template_offer_letter,
                submitters=[{
                    "email": landlord_email,
                    "name": landlord_name or "Landlord",
                    "role": "Landlord",
                }],
                prefill_fields={
                    "property_address": pfields.get("Address", ""),
                    "tenant_full_name": payload.tenant_full_name,
                    "monthly_rent": f"£{payload.monthly_rent:,.2f}",
                    "deposit_amount": f"£{payload.deposit_amount:,.2f}",
                    "start_date": payload.start_date.isoformat(),
                    "end_date": payload.end_date.isoformat() if payload.end_date else "Periodic",
                    "tenancy_term": payload.tenancy_term or "Periodic",
                },
                send_email=True,
                metadata={"property_id": property_id, "tenant_id": tenant_id, "kind": "offer_letter"},
            )
            submitters = docuseal_response.get("submitters") or []
            if submitters:
                docuseal_url = submitters[0].get("embed_src") or submitters[0].get("url")
    except Exception as e:  # noqa: BLE001
        logger.error("docuseal.offer_letter_failed err=%s", e)

    # 4b. Create the Offer row (Gap 5). Snapshots the commercial terms + the
    #     offer-letter envelope/submission id so the lifecycle (accept / reject
    #     / withdraw, competing offers) is tracked independently of
    #     Properties.Tenant. The landlord signing the offer letter (PG_04) — or
    #     the agent via /api/offers/{id}/accept — flips this Pending offer to
    #     Accepted and only then links the tenants to the property.
    offer_id: str | None = None
    try:
        from app.services.offers import create_offer  # noqa: PLC0415 — avoid load cycle
        envelope_id = (docuseal_response or {}).get("id")
        offer_id = create_offer(
            property_id=property_id,
            tenant_ids=all_tenant_ids,
            lead_tenant_name=payload.tenant_full_name,
            monthly_rent=payload.monthly_rent,
            rent_frequency=payload.rent_frequency,
            deposit_amount=payload.deposit_amount,
            holding_deposit=payload.holding_deposit,
            start_date=payload.start_date.isoformat(),
            end_date=payload.end_date.isoformat() if payload.end_date else None,
            tenancy_term=payload.tenancy_term,
            holding_deposit_deadline=hdd_iso,
            envelope_id=envelope_id,
            agent_email=find_stage_agent_email(4),
        )
    except Exception as e:  # noqa: BLE001
        logger.error("offer.row_create_failed err=%s", e)

    # 5. Submissions audit
    at.create(at.TableNames.SUBMISSIONS, {
        "Form Name": "PG_03 Offer",
        "Property": [property_id],
        "Submitted Date": date.today().isoformat(),
        "JSON Data": json.dumps(payload.model_dump(mode="json", exclude_none=True)),
    })

    # 6. Email agent
    agent_email = find_stage_agent_email(4)
    await send_agent_summary(
        agent_email or "",
        subject=f"Offer received — {payload.tenant_full_name} — {pfields.get('Address')}",
        template="E05_offer_received.html",
        context={
            "property_address": pfields.get("Address"),
            "tenancy_type": tenancy_type,
            "payload": payload.model_dump(mode="json", exclude_none=True),
            "docuseal_url": docuseal_url,
            "hmo": payload.number_of_occupants >= 3,
            "flags": ["HMO licence required"] if payload.number_of_occupants >= 3 else [],
        },
    )

    # 7. Gate check — PG_00 evaluates stage 5 (offer accepted) conditions.
    #    Expected to block initially because LL_Offer_Accepted only flips when
    #    DocuSeal callback in PG_04 confirms the landlord signed the offer
    #    letter; the block_reason surfaces that to the agent.
    offer_warnings: list[str] = []
    offer_actions: list[str] = []
    if total_tenants >= 3:
        offer_warnings.append(
            f"HMO threshold reached ({total_tenants} occupants). Confirm HMO licence is in place before move-in."
        )
        offer_actions.append("Confirm HMO licence (auto-added to checklist).")
    if not payload.anti_discrimination_confirmed and tenancy_type == "APT":
        offer_warnings.append("Anti-discrimination confirmation not ticked — APT compliance requires this before stage 5.")
    if payload.is_student or any(ct.is_student for ct in payload.co_tenants):
        offer_actions.append(
            "Student tenancy — Ground 4A notice required by 31 May 2026 (RRA 2025 Schedule 2)."
        )
    gate = await evaluate_gate(
        property_id, target_stage=5,
        warnings=offer_warnings,
        actions=offer_actions,
        source="PG_03 Offer",
    )

    return {
        "tenant_id": tenant_id,
        "offer_id": offer_id,
        "co_tenant_ids": co_tenant_ids,
        "violations": [],
        "docuseal_url": docuseal_url,
        "paragon_reference": paragon_ref,
        "hmo": total_tenants >= 3,
        "gate": gate.to_dict(),
    }
