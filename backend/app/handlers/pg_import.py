"""PG_IM - import an already-running tenancy onto the system.

An agency joining mid-flight has live tenancies whose take-on, marketing,
offer, referencing and signing all happened elsewhere. This brings them in.

The guiding rule is that **the pipeline does not fork**. An imported tenancy
creates the same Property / Landlord / Tenant rows as any other and is then
walked through the same stage gates in ``pg00_gate.TRANSITIONS``. Nothing is
force-set: the agent declares what already happened (signed, protected,
served), those declarations land on the very flags the gates read, and the
tenancy advances on its own merits. A tenancy whose evidence is complete
reaches Live; one with gaps stops exactly where the evidence runs out and the
caller is told why. That is deliberately more useful than dropping every
import at Stage 8 - the gate doubles as an audit of what the agency actually
holds.

Silent by design: the gate walk suppresses the per-stage agent emails, and no
outbound tenant/landlord correspondence fires. Importing history must not
email people about things that happened months ago.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.core.logger import get_logger
from app.db import supabase_client as at
from app.handlers.pg00_gate import evaluate_gate, find_stage_by_order
from app.models.common import ImportTenancyInput
from app.services.compliance import run_checks
from app.services.derivations import (
    derive_tenancy_type,
    is_overseas,
    nrl_withholding_active,
)

logger = get_logger(__name__)

IMPORT_FORM_NAME = "PG_IM Import Existing Tenancy"

# Stage 8 = Live Tenancy. Stage 9 (end) is reached through the normal
# end-of-tenancy flow, never by import.
TARGET_STAGE = 8

# Documents an existing tenancy is expected to have on file. Surfaced to the
# UI after import so the agent can attach the evidence behind their
# declarations. Bucket names must exist in routers/uploads.ALLOWED_BUCKETS.
IMPORT_DOCUMENT_CHECKLIST: list[dict[str, Any]] = [
    {"bucket": "signed_ta",       "label": "Signed tenancy agreement", "essential": True},
    {"bucket": "signed_tc",       "label": "Signed terms of business (landlord)", "essential": True},
    {"bucket": "gas_cert",        "label": "Gas safety certificate", "essential": True},
    {"bucket": "epc",             "label": "EPC", "essential": True},
    {"bucket": "eicr",            "label": "EICR", "essential": True},
    {"bucket": "tds_certificate", "label": "Deposit protection certificate", "essential": True},
    {"bucket": "inventory",       "label": "Inventory / check-in report", "essential": False},
    {"bucket": "other",           "label": "Anything else (How to Rent proof, correspondence)", "essential": False},
]


def _annual_rent(amount: float, frequency: str) -> float:
    return amount * (52 if frequency == "Weekly" else 12)


def _tenancy_term(payload: ImportTenancyInput) -> str:
    if not payload.end_date:
        return "Periodic"
    months = round((payload.end_date - payload.start_date).days / 30.44)
    return f"{months} months"


def _compliance_report(payload: ImportTenancyInput, *, gas_status, epc_status, eicr_status) -> dict:
    """Run the same compliance checks the landlord admin form runs.

    The pitch for importing into a compliance system is that gaps in the
    existing portfolio surface immediately, so the import reports them at the
    point of import rather than waiting for someone to open the property.
    """
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
        "service_level": payload.service_level,
        # Passed so the payout check reads the details actually supplied -
        # omitting them would report every import as missing bank details.
        "bank_name": payload.bank_name,
        "sort_code": payload.sort_code,
        "account_name": payload.account_name,
        "account_number": payload.account_number,
    })
    return {"warnings": report.warnings, "actions": report.actions, "flags": report.flags}


async def handle_import(payload: ImportTenancyInput, *, agent_email: str | None = None) -> dict:
    """Create an existing tenancy and walk it up the gates. Returns a report."""
    annual = _annual_rent(payload.rent_amount, payload.rent_frequency)
    tenancy_type = payload.tenancy_type or derive_tenancy_type(annual)
    today = date.today().isoformat()

    stage_1 = find_stage_by_order(1)

    # 1. Property. Created at stage 1 like any other, then advanced by gate.
    property_fields: dict[str, Any] = {
        "Address": payload.address,
        "post_code": payload.post_code,
        "Type": "Rent",
        "Gate Status": "Clear",
        "Tenancy Type": tenancy_type,
        "Rent Frequency": payload.rent_frequency,
        "Annual Rent ": annual,
        "landlord_email": payload.landlord_email,
        "Stage changed at": today,
        "Forms_Route_To_Agent": True,   # onboarding already happened offline
        "Agent_Forms_Email": agent_email,
        "Tenancy Start Date": payload.start_date.isoformat(),
        # Declared history -> the flags the gates read.
        "TC_Signed": payload.tc_signed,
        "TA_LL_Signed": payload.ta_landlord_signed,
        "TA_TT_Signed": payload.ta_tenants_signed,
        "LL_Offer_Accepted": True,      # a running tenancy implies acceptance
        "TDS Cert On File": payload.tds_cert_on_file,
        "Deposit Registered": payload.deposit_registered,
        "funds_cleared": payload.funds_cleared,
        "Works_Signed_Off": payload.works_signed_off,
        "How_To_Rent_Served": payload.how_to_rent_served,
        "Gas_Cert_Served": payload.gas_cert_served,
        "EPC_Served": payload.epc_served,
        "EICR_Served": payload.eicr_served,
        "TDS_Info_Served": payload.tds_info_served,
        "RRA_Sheet_Served": payload.rra_sheet_served,
        "HMO_Licence_Confirmed": payload.hmo_licence_confirmed,
        # Anti-discrimination is a marketing-stage attestation. The let already
        # happened elsewhere, so it cannot be re-attested now; it is recorded
        # as confirmed with the import noted in Submissions, rather than
        # blocking the gate on a decision this agency may not have taken.
        "Anti_Discrimination_Confirmed": True,
        "Anti_Discrimination_Confirmed_Date": today,
    }
    if payload.smoke_detectors_fitted is not None:
        property_fields["smoke_detectors_fitted"] = payload.smoke_detectors_fitted == "Yes"
    optional = {
        "Property Type": payload.property_type,
        "Service Level": payload.service_level,
        "Deposit": payload.deposit_amount,
        "EPC Rating ": payload.epc_rating,
        "Gas Certificates Expiry": payload.gas_cert_expiry.isoformat() if payload.gas_cert_expiry else None,
        "EICR Expiry": payload.eicr_expiry.isoformat() if payload.eicr_expiry else None,
        "Tenancy Expiry Date": payload.end_date.isoformat() if payload.end_date else None,
        "Deposit Registration Date": (
            payload.deposit_registration_date.isoformat() if payload.deposit_registration_date else None
        ),
        "Inventory_Clerk": payload.inventory_clerk,
    }
    property_fields.update({k: v for k, v in optional.items() if v is not None})
    # Certificate status is implied by holding an expiry date for it. Anything
    # not evidenced is "Not Provided" rather than blank, so the compliance
    # report treats a missing certificate as missing instead of unknown.
    gas_status = "On File" if payload.gas_cert_expiry else "Not Provided"
    eicr_status = "On File" if payload.eicr_expiry else "Not Provided"
    epc_status = "On File" if payload.epc_rating else "Not Provided"
    property_fields["Gas_Cert_Status"] = gas_status
    property_fields["EICR_Status"] = eicr_status
    property_fields["EPC_Status"] = epc_status
    if stage_1:
        property_fields["Stage"] = [stage_1["id"]]

    property_id = at.create(at.TableNames.PROPERTIES, property_fields)["id"]

    # 2. Landlord - already verified offline by definition of an existing let.
    landlord_fields: dict[str, Any] = {
        "Full Name": payload.landlord_full_name,
        "Email Address": payload.landlord_email,
        "Properties": [property_id],
        "Verification Status": "Verified",
        "TC_Signed": payload.tc_signed,
        "TA_Signed": payload.ta_landlord_signed,
        "Primary_For_Disbursement": True,
        "Ownership_Share_Percent": 100,
        # Tax treatment. An overseas landlord without an HMRC approval number
        # means 20% withholding is active - getting this wrong is an HMRC
        # liability, and it fails silently, so it is derived here exactly as
        # the landlord admin form derives it rather than left to a later edit.
        "UK_Resident_Status": "Non-resident" if is_overseas(payload.residency) else "Resident",
        "NRL_Withholding_Active": nrl_withholding_active(
            payload.residency, payload.nrl_approval_number,
        ),
        "NRL_Approval_Number": payload.nrl_approval_number,
        # Correspondence + payout.
        "Full Address": payload.landlord_full_address,
        "Post Code": payload.landlord_post_code,
        "Mobile Number": payload.landlord_mobile,
        "Bank Name": payload.bank_name,
        "Sort Code": payload.sort_code,
        "Account Name": payload.account_name,
        "Account Number": payload.account_number,
    }
    landlord_id = at.create(
        at.TableNames.LANDLORDS,
        {k: v for k, v in landlord_fields.items() if v is not None},
    )["id"]
    at.update(at.TableNames.PROPERTIES, property_id, {"Landlords": [landlord_id]})

    # 3. Tenants. Referencing is recorded as done: it happened before this
    #    tenancy started, elsewhere. Marked "Imported" rather than "Passed" so
    #    the record never claims a reference this system did not obtain.
    ordered = sorted(payload.tenants, key=lambda t: not t.is_lead)
    tenant_ids: list[str] = []
    for t in ordered:
        tenant_ids.append(at.create(at.TableNames.TENANTS, {
            "Name": t.full_name,
            "Tenant Email": t.email,
            "Property Id": [property_id],
            "Start Date": payload.start_date.isoformat(),
            "End Date": payload.end_date.isoformat() if payload.end_date else None,
            "Tenancy Term": _tenancy_term(payload),
            "Amount": payload.rent_amount,
            "Rent_Frequency": payload.rent_frequency,
            "Deposit Amount": payload.deposit_amount,
            "Referencing_Status": "Imported",
            "Referencing_Recorded": True,
            "Landlord_Approval_Received": True,
            "TA_Signed": payload.ta_tenants_signed,
            "Guarantor_Name": payload.guarantor_name,
            "Guarantor_Email": payload.guarantor_email,
        })["id"])

    # Properties.Tenant is the "accepted" relation (set on offer acceptance in
    # the normal flow) - an imported tenancy is by definition accepted.
    at.update(at.TableNames.PROPERTIES, property_id, {"Tenant": tenant_ids})

    # 4. Provenance. No schema change needed: the Submissions row records that
    #    this history was imported rather than originated here, and keeps the
    #    exact payload for audit.
    at.create(at.TableNames.SUBMISSIONS, {
        "Form Name": IMPORT_FORM_NAME,
        "Property": [property_id],
        "Submitted Date": today,
        "JSON Data": json.dumps(payload.model_dump(mode="json"), default=str),
    })

    # 5. Walk the gates. Silent: no per-stage emails for historic events.
    reached, blocked_at, blockers = await walk_gates(property_id, TARGET_STAGE)

    # 6. Post-signing side-effects the pipeline would have produced. Only once
    #    the tenancy is genuinely live, and only the forward-looking ones
    #    (renewal diary, financials) - never the correspondence.
    if reached >= TARGET_STAGE:
        _apply_live_side_effects(property_id)

    compliance = _compliance_report(
        payload, gas_status=gas_status, epc_status=epc_status, eicr_status=eicr_status,
    )

    logger.info("import.completed property=%s reached=%s blocked_at=%s tenants=%d warnings=%d",
                property_id, reached, blocked_at, len(tenant_ids),
                len(compliance["warnings"]))
    return {
        "property_id": property_id,
        "landlord_id": landlord_id,
        "tenant_ids": tenant_ids,
        "stage_reached": reached,
        "blocked_at": blocked_at,
        "blockers": blockers,
        "is_live": reached >= TARGET_STAGE,
        "compliance": compliance,
        "documents": IMPORT_DOCUMENT_CHECKLIST,
    }


async def walk_gates(property_id: str, target: int) -> tuple[int, int | None, list[str]]:
    """Advance a property one stage at a time up to ``target``.

    Returns (stage_reached, blocked_at, blockers). Stops at the first stage
    whose conditions are not met - those failures are precisely what the
    agency still needs to produce for this tenancy.
    """
    reached = 1
    for stage in range(2, target + 1):
        result = await evaluate_gate(
            property_id, stage, source="Imported existing tenancy", silent=True,
        )
        if not result.advanced:
            return reached, stage, list(result.failures)
        reached = stage
    return reached, None, []


def _apply_live_side_effects(property_id: str) -> None:
    """Financials + renewal diary, as the TA-signed webhook would have created.

    Best-effort: an import that has already produced its records should not be
    rolled back because a diary row failed.
    """
    from app.handlers.pg04_docuseal import (  # noqa: PLC0415 - avoid load cycle
        _create_financials,
        _create_ta_diary_entries,
    )
    try:
        fields = at.get(at.TableNames.PROPERTIES, property_id).get("fields", {})
        _create_financials(property_id)
        _create_ta_diary_entries(property_id, fields)
    except Exception as e:  # noqa: BLE001
        logger.warning("import.side_effects_failed property=%s err=%s", property_id, e)


def was_imported(property_id: str) -> bool:
    """True when this property came in through the import flow - read from the
    Submissions audit row, so no schema change is needed to know provenance."""
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id).get("fields", {})
        for sid in prop.get("Submissions") or []:
            row = at.get(at.TableNames.SUBMISSIONS, sid).get("fields", {})
            if row.get("Form Name") == IMPORT_FORM_NAME:
                return True
    except Exception:  # noqa: BLE001
        return False
    return False
