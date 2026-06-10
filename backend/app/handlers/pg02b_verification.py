"""PG_02b â€” Landlord verification (spec Â§6.3 / Â§5.3.1)."""
from __future__ import annotations

import json
from datetime import date

from app.config import settings
from app.core.email_client import send_agent_summary
from app.core.logger import get_logger
from app.db import supabase_client as at
from app.handlers.pg00_gate import evaluate_gate, find_stage_agent_email
from app.models.common import LandlordVerificationInput
from app.services.derivations import is_overseas, next_april_5

logger = get_logger(__name__)

_HIGH_RISK_SOURCES = {
    "high value property",
    "oversea company",
    "complex ownership structure",
}


def resolve_landlord(property_id: str, landlord_email: str | None) -> dict | None:
    """Find the correct landlord record for this verification submission.

    Strategy 1 (preferred): email match.
    Strategy 2 (fallback): first linked landlord still Pending Review.
    """
    if landlord_email:
        rec = at.find_first(at.TableNames.LANDLORDS, at.eq("Email Address", landlord_email))
        if rec:
            return rec
    prop = at.get(at.TableNames.PROPERTIES, property_id)
    linked = prop.get("fields", {}).get("Landlords") or []
    for lid in linked:
        rec = at.get(at.TableNames.LANDLORDS, lid)
        if rec.get("fields", {}).get("Verification Status") == "Pending Review":
            return rec
    return None


async def handle_verification(
    property_id: str,
    landlord_email: str | None,
    payload: LandlordVerificationInput,
) -> dict:
    landlord = resolve_landlord(property_id, landlord_email)
    if not landlord:
        raise ValueError("Could not match landlord for this verification submission")
    landlord_id = landlord["id"]

    isCompany = (payload.individual_or_company or "").lower().startswith("comp")
    # Wave B: residency is no longer collected on this form. Source it from the
    # UK_Resident_Status PG_02 already wrote to the landlord record; only fall
    # back to a payload value (legacy Tally webhook) if the record lacks one.
    stored_status = (landlord.get("fields", {}).get("UK_Resident_Status") or "").strip()
    if stored_status:
        isOverseas = stored_status == "Non-resident"
    else:
        isOverseas = is_overseas(payload.residency)
    sof_lower = (payload.source_of_funds or "").strip().lower()
    edd = sof_lower in _HIGH_RISK_SOURCES

    # 1. Update landlord
    fields: dict = {
        "Individual or Company": payload.individual_or_company,
        "UK_Resident_Status": "Resident" if not isOverseas else "Non-resident",
        "ID Document Type": payload.id_document_type,
        "ID Document URL": payload.id_document_upload,
        "Visa Snapshot URL": payload.visa_snapshot,
        "Address Doc Type": payload.address_doc_type,
        "Address Document URL": payload.address_doc_upload,
        "Ownership Document URL": payload.ownership_doc_upload,
        "Company Name": payload.company_name,
        "Company Reg Number": payload.company_reg_number,
        "Company Reg Address": payload.company_reg_address,
        "Director Name": payload.director_name,
        "Incorporation Doc URL": payload.certificate_of_incorporation,
        "Bank Statements URL": payload.bank_statements_upload,
        "Source of Funds": payload.source_of_funds,
        "Purchase Explanation": payload.purchase_explanation,
        # Verification Status singleSelect in Airtable only has Pending Review
        # / Approved / Rejected â€” the EDD distinction is carried on the
        # Gate_Log warning + the agent summary email instead.
        "Verification Status": "Pending Review",
        "ID_Name_Match": "Pending",
        "AML_Check_Date": date.today().isoformat(),
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    at.update(at.TableNames.LANDLORDS, landlord_id, fields)

    # 2. Overseas â†’ NRL diary (once) â€” Diary table has no Landlord link, so
    #    landlord context is embedded in Alert_Message.
    if isOverseas and not landlord.get("fields", {}).get("NRL_Tax_Cert_Diary_Set"):
        ll_name = landlord.get("fields", {}).get("Full Name", "landlord")
        at.create(at.TableNames.DIARY, {
            "Diary_Type": "NRL Tax Cert",
            "Property": [property_id],
            "Diary Date": date.today().isoformat(),
            "Alert_Date": next_april_5().isoformat(),
            "Alert_Message": f"Issue NRL tax certificate to {ll_name} (verification path).",
            "Assigned_To": settings.lesley_email,
            "Fired": False,
        })
        at.update(at.TableNames.LANDLORDS, landlord_id, {"NRL_Tax_Cert_Diary_Set": True})

    # 3. Submissions audit (live SUBMISSIONS table has no Landlord link field)
    at.create(at.TableNames.SUBMISSIONS, {
        "Form Name": "PG_02b Landlord Verification",
        "Property": [property_id],
        "Submitted Date": date.today().isoformat(),
        "JSON Data": json.dumps(payload.model_dump(mode="json", exclude_none=True)),
    })

    # 4. Notify agent
    agent_email = find_stage_agent_email(2)
    template = "E04_EDD_verification.html" if edd else "E04_verification_received.html"
    await send_agent_summary(
        agent_email or "",
        subject=f"Verification received â€” {payload.individual_or_company} path",
        template=template,
        context={
            "landlord_id": landlord_id,
            "is_company": isCompany,
            "is_overseas": isOverseas,
            "edd": edd,
            "payload": payload.model_dump(mode="json", exclude_none=True),
            "flags": ["Enhanced Due Diligence required"] if edd else [],
            "warnings": [],
            "actions": ["Review AML pack and confirm ID name match."],
        },
    )

    # 5. Gate check â€” re-evaluate stage 3 conditions so any blockers (e.g.
    #    T&C not yet signed) are surfaced to the agent now that verification
    #    is complete. Also surface missing AML-pack pieces as warnings so the
    #    agent can chase before approving the landlord.
    review_actions: list[str] = ["Review AML pack and confirm ID name match."]
    review_warnings: list[str] = []
    if edd:
        review_warnings.append("Enhanced Due Diligence required â€” high-risk source of funds.")
    if not payload.id_document_upload:
        review_warnings.append("ID document not uploaded.")
    if not payload.address_doc_upload:
        review_warnings.append("Proof of address not uploaded.")
    if not payload.ownership_doc_upload:
        review_warnings.append("Proof of ownership not uploaded.")
    if isOverseas and not payload.visa_snapshot:
        review_warnings.append("Overseas landlord â€” visa / BRP snapshot not uploaded.")
    if isCompany:
        if not (payload.director_name or "").strip():
            review_warnings.append("Company landlord â€” director name missing.")
        if not payload.certificate_of_incorporation:
            review_warnings.append("Company landlord â€” certificate of incorporation not uploaded.")
        if not payload.bank_statements_upload:
            review_warnings.append("Company landlord â€” bank statements not uploaded.")
        if not (payload.company_reg_number or "").strip():
            review_warnings.append("Company landlord â€” company registration number missing.")
    gate = await evaluate_gate(
        property_id, target_stage=3,
        warnings=review_warnings,
        actions=review_actions,
        source="PG_02b Landlord Verification",
    )

    return {
        "landlord_id": landlord_id,
        "edd": edd,
        "is_overseas": isOverseas,
        "is_company": isCompany,
        "gate": gate.to_dict(),
    }
