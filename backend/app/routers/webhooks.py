"""Legacy webhook endpoints — kept for backwards compatibility with Tally and
DocuSeal callbacks. New deployments should drive everything through
`/api/forms/*`, but Tally-hosted forms still POST here.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import EmailStr

from app.config import settings
from app.core.docuseal_client import verify_webhook_signature
from app.core.logger import get_logger
from app.handlers.pg01_takeon import handle_takeon
from app.handlers.pg02_admin import handle_admin
from app.handlers.pg02b_verification import handle_verification
from app.handlers.pg03_offer import handle_offer
from app.handlers.pg04_docuseal import handle_docuseal_event
from app.handlers.pg05_tenant_pack import handle_tenant_pack
from app.handlers.pg06_scheduler import run_scheduler
from app.handlers.pg07_rra_batch import handle_rra_batch
from app.models.common import LandlordAdminInput, LandlordVerificationInput, OfferInput, PropertyTakeonInput
from app.parsers.tally_parser import get_by_label, get_hidden

router = APIRouter(tags=["webhooks"])
logger = get_logger(__name__)


def _tally_fields(body: dict) -> list[dict]:
    return (body.get("data") or {}).get("fields") or body.get("fields") or []


# ---------------------------------------------------------------------------
# Tally — PG_01 take-on
# ---------------------------------------------------------------------------
@router.post("/webhook/property-takeon")
async def webhook_property_takeon(req: Request) -> dict:
    body = await req.json()
    fields = _tally_fields(body)
    payload = PropertyTakeonInput(
        address=get_by_label(fields, "property address") or get_by_label(fields, "address"),
        post_code=get_by_label(fields, "post code") or get_by_label(fields, "postcode"),
        landlord_full_name=get_by_label(fields, "landlord full name") or get_by_label(fields, "landlord name"),
        landlord_email=get_by_label(fields, "landlord email"),
        send_admin_form=(get_by_label(fields, "send admin form") or "Yes").lower().startswith("yes"),
        asking_rent_pcm=_to_float(get_by_label(fields, "rent")),
    )
    return await handle_takeon(payload)


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("£", ""))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tally — PG_02 admin
# ---------------------------------------------------------------------------
@router.post("/webhook/landlord-admin")
async def webhook_landlord_admin(req: Request) -> dict:
    body = await req.json()
    fields = _tally_fields(body)
    property_id = get_hidden(fields, "id")
    if not property_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hidden 'id' field missing")
    payload = LandlordAdminInput(
        property_post_code=get_by_label(fields, "property postal code") or "",
        block_manager_name=get_by_label(fields, "block manager name"),
        block_manager_address=get_by_label(fields, "block manager address"),
        block_manager_postal_code=get_by_label(fields, "block manager postal code"),
        block_manager_contact=get_by_label(fields, "block manager contact"),
        block_manager_email=get_by_label(fields, "block manager email"),
        consent_sublet=get_by_label(fields, "consent to sub-let"),
        consent_mortgagor=get_by_label(fields, "consent from mortgagor"),
        mortgage_consent_upload=get_by_label(fields, "mortgage consent upload"),
        landlord_full_name=get_by_label(fields, "landlord full name") or "",
        landlord_full_address=get_by_label(fields, "landlord full address") or "",
        landlord_post_code=get_by_label(fields, "landlord post code") or "",
        landlord_mobile=get_by_label(fields, "landlord mobile") or "",
        landlord_email=get_by_label(fields, "landlord email") or "",
        residency=get_by_label(fields, "residency status") or "",
        nrl_approval_number=get_by_label(fields, "nrl approval number"),
        bank_name=get_by_label(fields, "bank name"),
        sort_code=get_by_label(fields, "sort code"),
        account_name=get_by_label(fields, "account name"),
        account_number=get_by_label(fields, "account number"),
        has_photos=get_by_label(fields, "has photos"),
        auth_photos=get_by_label(fields, "auth photos"),
        has_inventory=get_by_label(fields, "has inventory"),
        auth_inventory=get_by_label(fields, "auth inventory"),
        property_type=get_by_label(fields, "property type"),
        tenure=get_by_label(fields, "tenure"),
        head_lease_upload=get_by_label(fields, "head lease upload"),
        freeholder_consent=get_by_label(fields, "freeholder consent"),
        freeholder_consent_upload=get_by_label(fields, "freeholder consent upload"),
        who_manages_property=get_by_label(fields, "who manages property"),
        third_party_manager=get_by_label(fields, "third party manager details"),
        insurance_in_place=get_by_label(fields, "insurance in place"),
        has_gas_cert=get_by_label(fields, "has gas safety cert"),
        arrange_gas_cert=get_by_label(fields, "arrange gas cert"),
        gas_cert_expiry=get_by_label(fields, "gas cert expiry date"),
        gas_cert_upload=get_by_label(fields, "gas cert upload"),
        has_epc=get_by_label(fields, "has epc"),
        arrange_epc=get_by_label(fields, "arrange epc"),
        epc_rating=get_by_label(fields, "epc rating"),
        epc_upload=get_by_label(fields, "epc upload"),
        has_eicr=get_by_label(fields, "has eicr"),
        arrange_eicr=get_by_label(fields, "arrange eicr"),
        eicr_expiry=get_by_label(fields, "eicr expiry date"),
        eicr_upload=get_by_label(fields, "eicr upload"),
        smoke_detectors_fitted=get_by_label(fields, "smoke detectors fitted"),
        furniture_fire_regs=get_by_label(fields, "furniture fire regs"),
        supply_keys=get_by_label(fields, "supply keys"),
        alternative_access=get_by_label(fields, "alternative access"),
    )
    return await handle_admin(property_id, payload)


# ---------------------------------------------------------------------------
# Tally — PG_02b verification
# ---------------------------------------------------------------------------
@router.post("/webhook/landlord-verification")
async def webhook_landlord_verification(req: Request) -> dict:
    body = await req.json()
    fields = _tally_fields(body)
    property_id = get_hidden(fields, "id")
    landlord_email = get_hidden(fields, "email")
    if not property_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hidden 'id' field missing")
    payload = LandlordVerificationInput(
        individual_or_company=get_by_label(fields, "individual or company") or "Individual",
        residency=get_by_label(fields, "residency status") or "",
        id_document_type=get_by_label(fields, "id document type"),
        id_document_upload=get_by_label(fields, "id document upload"),
        visa_snapshot=get_by_label(fields, "visa snapshot"),
        address_doc_type=get_by_label(fields, "address doc type"),
        address_doc_upload=get_by_label(fields, "address doc upload"),
        ownership_doc_upload=get_by_label(fields, "ownership doc upload"),
        company_name=get_by_label(fields, "company name"),
        company_reg_number=get_by_label(fields, "company reg number"),
        company_reg_address=get_by_label(fields, "company reg address"),
        certificate_of_incorporation=get_by_label(fields, "certificate of incorporation"),
        director_name=get_by_label(fields, "director name"),
        source_of_funds=get_by_label(fields, "source of fund"),
        purchase_explanation=get_by_label(fields, "purchase explanation"),
        bank_statements_upload=get_by_label(fields, "bank statements upload"),
    )
    return await handle_verification(property_id, landlord_email, payload)


# ---------------------------------------------------------------------------
# Tally — PG_03 offer
# ---------------------------------------------------------------------------
@router.post("/webhook/offer")
async def webhook_offer(req: Request) -> dict:
    body = await req.json()
    fields = _tally_fields(body)
    property_id = get_hidden(fields, "id")
    if not property_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hidden 'id' field missing")
    payload = OfferInput(
        tenant_full_name=get_by_label(fields, "tenant full name") or "",
        tenant_email=get_by_label(fields, "tenant email") or "",
        tenant_address=get_by_label(fields, "tenant address"),
        start_date=get_by_label(fields, "start date"),
        end_date=get_by_label(fields, "end date"),
        tenancy_term=get_by_label(fields, "tenancy term"),
        monthly_rent=_to_float(get_by_label(fields, "monthly rent")) or 0.0,
        deposit_amount=_to_float(get_by_label(fields, "deposit amount")) or 0.0,
        holding_deposit=_to_float(get_by_label(fields, "holding deposit")) or 0.0,
        rent_in_advance_months=int(_to_float(get_by_label(fields, "rent in advance")) or 0),
        break_clause=get_by_label(fields, "break clause"),
        renewal_terms=get_by_label(fields, "renewal terms"),
        special_conditions=get_by_label(fields, "special conditions"),
        number_of_occupants=int(_to_float(get_by_label(fields, "number of occupants")) or 1),
        guarantor_name=get_by_label(fields, "guarantor name"),
        guarantor_address=get_by_label(fields, "guarantor address"),
        guarantor_email=get_by_label(fields, "guarantor email"),
        is_student=(get_by_label(fields, "is student") or "No").lower().startswith("yes"),
    )
    return await handle_offer(property_id, payload)


# ---------------------------------------------------------------------------
# DocuSeal webhook
# ---------------------------------------------------------------------------
@router.post("/webhook/docuseal-signed")
async def webhook_docuseal(req: Request, x_docuseal_signature: str | None = Header(default=None)) -> dict:
    raw = await req.body()
    if not verify_webhook_signature(raw, x_docuseal_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid DocuSeal signature")
    body = json.loads(raw)
    return await handle_docuseal_event(body)


# ---------------------------------------------------------------------------
# DocuSign Connect webhook
# ---------------------------------------------------------------------------
# DocuSign Admin → Connect → New Configuration (JSON) is configured to POST
# envelope events here. We verify the optional HMAC header (X-DocuSign-Signature-1
# when "Include HMAC Signature" is on), normalise the payload, and hand off
# to the same PG_04 handler the DocuSeal webhook uses — so the downstream
# Properties/Landlords/Tenants writes are single-pathed regardless of provider.
@router.post("/webhook/docusign")
async def webhook_docusign(
    req: Request,
    x_docusign_signature_1: str | None = Header(default=None, convert_underscores=True),
) -> dict:
    import base64  # noqa: PLC0415 — local imports keep import-time graph slim
    import hashlib
    import hmac
    from app.core.signing import normalise_docusign_event  # noqa: PLC0415

    raw = await req.body()
    secret = settings.docusign_connect_hmac_secret or ""
    if secret:
        if not x_docusign_signature_1:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-DocuSign-Signature-1 header")
        # DocuSign Connect signs with HMAC-SHA256 and sends the result base64-encoded
        # (NOT hex). Compute both and accept either form so we tolerate any future
        # signing-format flip without re-deploying. The actual signature
        # DocuSign sends is the base64 form.
        mac = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256)
        expected_b64 = base64.b64encode(mac.digest()).decode()
        expected_hex = mac.hexdigest()
        sent = x_docusign_signature_1.strip()
        if not (hmac.compare_digest(expected_b64, sent) or
                hmac.compare_digest(expected_hex, sent.lower())):
            # Log enough detail to debug a secret mismatch without leaking the secret.
            logger.warning(
                "docusign.hmac.mismatch sent_prefix=%s expected_b64_prefix=%s body_len=%d",
                sent[:8], expected_b64[:8], len(raw),
            )
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid DocuSign signature")
    else:
        # No secret configured — log loud so dev knows. Connect will still
        # accept the response so envelopes don't retry forever.
        logger.warning("DocuSign Connect HMAC secret not set — accepting unverified webhook")

    try:
        body = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid JSON: {e}")

    normalised = normalise_docusign_event(body)

    # Connect can omit custom fields from the payload entirely if the config
    # doesn't tick "Include Custom Fields". Fall back to an API fetch so the
    # downstream handler always has metadata.property_id to bind back to the
    # right Property record. Costs one extra DocuSign GET per webhook.
    envelope_id = normalised["data"]["submission_id"]
    if envelope_id and not normalised["data"].get("metadata", {}).get("property_id"):
        try:
            from app.core.docusign_client import get_envelope_custom_fields  # noqa: PLC0415
            cf_resp = await get_envelope_custom_fields(envelope_id)
            extra = {
                cf.get("name"): cf.get("value")
                for cf in (cf_resp.get("textCustomFields") or [])
                if cf.get("name")
            }
            if extra:
                normalised["data"]["metadata"] = {**normalised["data"].get("metadata", {}), **extra}
                logger.info("docusign.cf_fallback envelope=%s keys=%s", envelope_id, list(extra))
        except Exception as e:  # noqa: BLE001
            logger.warning("docusign.cf_fallback_failed envelope=%s err=%s", envelope_id, e)

    result = await handle_docuseal_event(normalised)
    return {"docusign": True, "envelope_id": envelope_id, "outcome": result}


# Manual fallback for when ngrok isn't running. Agent UI can hit this to
# force a re-check; backend pulls the envelope state from DocuSign and runs
# the same normalisation/handler if it's completed.
@router.post("/webhook/docusign/poll/{envelope_id}")
async def docusign_poll(envelope_id: str) -> dict:
    from app.core.docusign_client import (  # noqa: PLC0415
        get_envelope_status,
        get_envelope_recipients,
        get_envelope_custom_fields,
    )
    from app.core.signing import normalise_docusign_event  # noqa: PLC0415

    summary    = await get_envelope_status(envelope_id)
    recipients = await get_envelope_recipients(envelope_id)
    custom     = await get_envelope_custom_fields(envelope_id)

    # Stitch into a Connect-shaped payload so the same normaliser handles it.
    stitched = {
        "event": "envelope-completed" if (summary.get("status") == "completed") else "envelope-updated",
        "data": {
            "envelopeId": envelope_id,
            "envelopeSummary": {
                **summary,
                "recipients":   recipients,
                "customFields": custom,
            },
        },
    }
    normalised = normalise_docusign_event(stitched)
    if summary.get("status") != "completed":
        # Don't run the handler unless it's actually done — otherwise we'd
        # flip TC_Signed prematurely on partial signs.
        return {"envelope_id": envelope_id, "status": summary.get("status"), "handled": False}
    result = await handle_docuseal_event(normalised)
    return {"envelope_id": envelope_id, "status": "completed", "handled": True, "outcome": result}


# ---------------------------------------------------------------------------
# Internal cron / RRA batch
# ---------------------------------------------------------------------------
@router.post("/internal/run-scheduler")
async def internal_scheduler(token: str) -> dict:
    if token != settings.scheduler_internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid token")
    return await run_scheduler()


@router.post("/webhook/rra-batch")
async def webhook_rra_batch(token: str) -> dict:
    if token != settings.scheduler_internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid token")
    return await handle_rra_batch()


@router.post("/webhook/tenant-pack")
async def webhook_tenant_pack(req: Request) -> dict:
    body = await req.json()
    pid = body.get("property_id")
    if not pid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "property_id required")
    return await handle_tenant_pack(pid)
