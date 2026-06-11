"""PG_01 â€” Property take-on handler (spec Â§6.1).

Driven by either:
- the internal POST /api/forms/property-takeon endpoint (preferred), or
- the legacy Tally webhook POST /webhook/property-takeon.

Both call into `handle_takeon` with a normalised `PropertyTakeonInput`.
"""
from __future__ import annotations

import json
from datetime import date

from app.config import settings
from app.core.auth import FormTokenPayload, create_form_token
from app.core.email_client import send_admin_form_link
from app.core.logger import get_logger
from app.db import supabase_client as at
from app.handlers.pg00_gate import evaluate_gate, find_stage_by_order
from app.models.common import PropertyTakeonInput
from app.services.derivations import derive_tenancy_type

logger = get_logger(__name__)


async def handle_takeon(payload: PropertyTakeonInput) -> dict:
    # Annualise the rent based on the chosen frequency (Weekly Ã— 52 or
    # Monthly Ã— 12) â€” drives APT vs. Common Law classification per the
    # Housing Act 1988 Â£100k threshold.
    if payload.asking_rent_pcm:
        multiplier = 52 if payload.rent_frequency == "Weekly" else 12
        annual_rent = payload.asking_rent_pcm * multiplier
    else:
        annual_rent = None
    tenancy_type = derive_tenancy_type(annual_rent)

    stage_1 = find_stage_by_order(1)
    stage_1_id = stage_1["id"] if stage_1 else None

    # 1. Create Property record. Note the trailing space on "Annual Rent " â€”
    #    that's how the field is named in the live Airtable base.
    property_fields: dict = {
        "Address": payload.address,
        "post_code": payload.post_code,
        "Type": "Rent",
        "Gate Status": "Clear",
        "Tenancy Type": tenancy_type,
        "Rent Frequency": payload.rent_frequency,
        "landlord_email": payload.landlord_email,
        "Stage changed at": date.today().isoformat(),
    }
    if annual_rent is not None:
        property_fields["Annual Rent "] = annual_rent
    if stage_1_id:
        property_fields["Stage"] = [stage_1_id]
    property_record = at.create(at.TableNames.PROPERTIES, property_fields)
    property_id = property_record["id"]

    # 2. Create Landlord stub
    landlord_fields = {
        "Full Name": payload.landlord_full_name,
        "Email Address": payload.landlord_email,
        "Properties": [property_id],
        "Verification Status": "Pending Review",
        "TA_Signed": False,
        "TC_Signed": False,
        "Primary_For_Disbursement": False,
        "Ownership_Share_Percent": 0,
    }
    landlord_record = at.create(at.TableNames.LANDLORDS, landlord_fields)

    # 3. Link landlord back to property
    at.update(at.TableNames.PROPERTIES, property_id, {
        "Landlords": [landlord_record["id"]],
    })

    # 4. Submissions audit row
    at.create(at.TableNames.SUBMISSIONS, {
        "Form Name": "PG_01 Agent Add Property",
        "Property": [property_id],
        "Submitted Date": date.today().isoformat(),
        "JSON Data": json.dumps(payload.model_dump(mode="json")),
    })

    # 5. Send admin form link to landlord (internal route)
    if payload.send_admin_form:
        token = create_form_token(FormTokenPayload(
            property_id=property_id,
            form="landlord_admin",
            email=payload.landlord_email,
            landlord_id=landlord_record["id"],
        ))
        form_url = f"{settings.frontend_base_url}/landlord/admin?token={token}"
        await send_admin_form_link(
            payload.landlord_email,
            property_address=payload.address,
            form_url=form_url,
        )

    # 6. Gate check â€” should pass immediately (landlord just linked)
    gate = await evaluate_gate(property_id, target_stage=2)

    # NOTE (billing): with pay-first take-on, the GBP 50 fee is collected
    # BEFORE this handler runs â€” the forms router stores the payload as a
    # pending intent and only calls handle_takeon once Stripe confirms payment
    # (services/billing.mark_paid_and_fulfill). This function itself is
    # payment-agnostic.
    return {
        "property_id": property_id,
        "landlord_id": landlord_record["id"],
        "tenancy_type": tenancy_type,
        "gate": gate.to_dict(),
    }
