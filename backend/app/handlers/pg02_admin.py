"""PG_02 â€” Landlord admin form (spec Â§6.2)."""
from __future__ import annotations

import json
from datetime import date

from app.config import settings
from app.core.auth import FormTokenPayload, create_form_token
from app.core.email_client import send_agent_summary, send_verification_link
from app.core.logger import get_logger
from app.db import supabase_client as at
from app.handlers.pg00_gate import evaluate_gate, find_stage_agent_email, find_stage_by_order
from app.models.common import LandlordAdminInput
from app.services.compliance import run_checks
from app.services.derivations import (
    derive_cert_status,
    derive_service_level,
    is_overseas,
    next_april_5,
    nrl_withholding_active,
)

logger = get_logger(__name__)


async def handle_admin(property_id: str, payload: LandlordAdminInput) -> dict:
    # 0. Fetch property so we can quote the real Address in emails/templates
    existing_prop = at.get(at.TableNames.PROPERTIES, property_id)
    property_address = existing_prop.get("fields", {}).get("Address", "")

    # 1. Derivations
    gas_status = derive_cert_status(payload.has_gas_cert, payload.arrange_gas_cert)
    epc_status = derive_cert_status(payload.has_epc, payload.arrange_epc)
    eicr_status = derive_cert_status(payload.has_eicr, payload.arrange_eicr)
    service_level = derive_service_level(payload.who_manages_property)
    isNRL = is_overseas(payload.residency)
    nrl_active = nrl_withholding_active(payload.residency, payload.nrl_approval_number)

    # 2. Update Properties record. Only the columns that exist in the live
    #    Airtable schema are written here â€” the rest of the Tally-parity
    #    payload is preserved verbatim in the SUBMISSIONS audit row (step 3).
    property_fields: dict = {
        "Service Level": service_level,
        "Property Type": payload.property_type,
        "EPC Rating ": payload.epc_rating,  # live Airtable field has trailing space
        "Gas Certificates Expiry": payload.gas_cert_expiry.isoformat() if payload.gas_cert_expiry else None,
        "EICR Expiry": payload.eicr_expiry.isoformat() if payload.eicr_expiry else None,
        "Gas_Cert_Status": gas_status,
        "EPC_Status": epc_status,
        "EICR_Status": eicr_status,
        "mortgage_consent_url": payload.mortgage_consent_upload,
        "head_lease_url": payload.head_lease_upload,
        "freeholder_consent_url": payload.freeholder_consent_upload,
        "Insurance_provider": payload.insurance_provider,
        "Insurance_policy_number": payload.insurance_policy_number,
        "Insurance_certificate_url": payload.insurance_cert_upload,
        "smoke_detectors_fitted": payload.smoke_detectors_fitted == "Yes",
        "Gate Status": "Clear",
        "Stage changed at": date.today().isoformat(),
    }
    # Strip None values so we don't overwrite existing data with blanks
    property_fields = {k: v for k, v in property_fields.items() if v is not None}
    at.update(at.TableNames.PROPERTIES, property_id, property_fields)

    # 3. Submissions audit
    at.create(at.TableNames.SUBMISSIONS, {
        "Form Name": "PG_02 Landlord Admin",
        "Property": [property_id],
        "Submitted Date": date.today().isoformat(),
        "JSON Data": json.dumps(payload.model_dump(mode="json", exclude_none=True)),
    })

    # 4. Upsert landlord
    landlord_fields = {
        "Full Name": payload.landlord_full_name,
        "Email Address": payload.landlord_email,
        "Mobile Number": payload.landlord_mobile,
        "Full Address": payload.landlord_full_address,
        "Post Code": payload.landlord_post_code,
        "UK_Resident_Status": "Resident" if not isNRL else "Non-resident",
        "NRL_Withholding_Active": nrl_active,
        "NRL_Approval_Number": payload.nrl_approval_number,
        "Bank Name": payload.bank_name,
        "Sort Code": payload.sort_code,
        "Account Name": payload.account_name,
        "Account Number": payload.account_number,
        "Block Manager Name": payload.block_manager_name,
        "Block Manager Address": payload.block_manager_address,
        "Block Manager Postal Code": payload.block_manager_postal_code,
        "Block Manager Contact": payload.block_manager_contact,
        "Block Manager Email": payload.block_manager_email,
        "Verification Status": "Pending Review",
    }
    landlord_fields = {k: v for k, v in landlord_fields.items() if v is not None}

    existing = at.find_first(at.TableNames.LANDLORDS, at.eq("Email Address", payload.landlord_email))
    if existing:
        at.update(at.TableNames.LANDLORDS, existing["id"], landlord_fields)
        landlord_id = existing["id"]
    else:
        landlord_fields["Properties"] = [property_id]
        landlord_id = at.create(at.TableNames.LANDLORDS, landlord_fields)["id"]
        # link to property
        at.update(at.TableNames.PROPERTIES, property_id, {"Landlords": [landlord_id]})

    # 5. Compliance checks
    report = run_checks(admin={
        "residency": payload.residency,
        "nrl_approval_number": payload.nrl_approval_number,
        "gas_cert_status": gas_status,
        "gas_cert_expiry": payload.gas_cert_expiry,
        "epc_status": epc_status,
        "epc_rating": payload.epc_rating,
        "eicr_status": eicr_status,
        "eicr_expiry": payload.eicr_expiry,
        "smoke_detectors": payload.smoke_detectors_fitted,
        "furniture_fire": payload.furniture_fire_regs,
        "consent_mortgagor": payload.consent_mortgagor,
        "mortgage_consent_upload": payload.mortgage_consent_upload,
        "tenure": payload.tenure,
        "freeholder_consent": payload.freeholder_consent,
        "insurance_in_place": payload.insurance_in_place,
        "has_photos": payload.has_photos,
        "auth_photos": payload.auth_photos,
        "supply_keys": payload.supply_keys,
        "alt_access": payload.alternative_access,
        "has_inventory": payload.has_inventory,
        "auth_inventory": payload.auth_inventory,
        "service_level": service_level,
        "who_manages_property": payload.who_manages_property,
        "third_party_manager": payload.third_party_manager,
        "bank_name": payload.bank_name,
        "sort_code": payload.sort_code,
        "account_name": payload.account_name,
        "account_number": payload.account_number,
    })

    # 6. NRL diary (only once) â€” live Airtable's Diary table has no Landlord
    #    link field, so the landlord context goes into Alert_Message instead.
    if isNRL:
        landlord = at.get(at.TableNames.LANDLORDS, landlord_id)
        if not landlord.get("fields", {}).get("NRL_Tax_Cert_Diary_Set"):
            at.create(at.TableNames.DIARY, {
                "Diary_Type": "NRL Tax Cert",
                "Property": [property_id],
                "Diary Date": date.today().isoformat(),
                "Alert_Date": next_april_5().isoformat(),
                "Alert_Message": f"Issue NRL tax certificate to {payload.landlord_full_name} ({payload.landlord_email}).",
                "Assigned_To": settings.lesley_email,
                "Fired": False,
            })
            at.update(at.TableNames.LANDLORDS, landlord_id, {"NRL_Tax_Cert_Diary_Set": True})

    # 7. Notify agent â€” include the full submitted payload so the agent can
    #    review every field directly in their inbox.
    agent_email = find_stage_agent_email(2)
    submission_fields = _payload_review_rows(payload)
    await send_agent_summary(
        agent_email or "",
        subject=f"Landlord admin received â€” {payload.landlord_full_name} â€” {property_address}",
        template="E02_admin_received.html",
        context={
            "property_address": property_address,
            "landlord_full_name": payload.landlord_full_name,
            "landlord_email": payload.landlord_email,
            "gas_status": gas_status,
            "epc_status": epc_status,
            "eicr_status": eicr_status,
            "service_level": service_level,
            "is_nrl": isNRL,
            "flags": report.flags,
            "warnings": report.warnings,
            "actions": report.actions,
            "submission_fields": submission_fields,
        },
    )

    # 8. Send verification form link — to the agent if onboarding was routed to
    #    them at take-on (send_admin_form was off), otherwise to the landlord.
    token = create_form_token(FormTokenPayload(
        property_id=property_id,
        form="landlord_verification",
        email=payload.landlord_email,
        landlord_id=landlord_id,
    ))
    form_url = f"{settings.frontend_base_url}/landlord/verify?token={token}"
    _prop_fields = existing_prop.get("fields", {})
    _agent_forms_email = _prop_fields.get("Agent_Forms_Email")
    if _prop_fields.get("Forms_Route_To_Agent") and _agent_forms_email:
        await send_verification_link(
            _agent_forms_email,
            property_address=property_address,
            form_url=form_url,
            for_agent=True,
        )
    else:
        await send_verification_link(
            payload.landlord_email,
            property_address=property_address,
            form_url=form_url,
        )

    # 9. Gate check â€” PG_00 is the exit condition for stage 2. Logs any
    #    blockers (e.g. T&C not yet signed) to the agent.
    #    The compliance report's non-blocking warnings/actions ride along on
    #    the same Gate_Log row so the property page can surface them.
    gate = await evaluate_gate(
        property_id, target_stage=3,
        warnings=report.warnings,
        actions=report.actions,
        source="PG_02 Landlord Admin",
    )

    return {
        "property_id": property_id,
        "landlord_id": landlord_id,
        "compliance": report.to_dict(),
        "service_level": service_level,
        "gate": gate.to_dict(),
    }


def _payload_review_rows(payload: LandlordAdminInput) -> list[tuple[str, str]]:
    """Flatten the admin submission to (label, value) rows for email rendering.

    Strips None/empty values, formats booleans, dates and URLs as readable text.
    """
    rows: list[tuple[str, str]] = []
    for name, value in payload.model_dump(mode="json", exclude_none=True).items():
        if value in (None, "", []):
            continue
        label = name.replace("_", " ").strip().capitalize()
        if isinstance(value, bool):
            rows.append((label, "Yes" if value else "No"))
        else:
            rows.append((label, str(value)))
    return rows
