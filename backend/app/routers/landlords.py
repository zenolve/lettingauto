"""Landlord-level CRUD — currently just the flags catalog + PATCH used by the
LandlordFlags panel on the property detail page.

Mirrors the shape of properties.py:flags but with a landlord-specific
allowlist and one extra field type — ``single_select`` for the Airtable
singleSelect columns ``ID_Name_Match`` and ``Verification Status``. The
catalog declares each option so the UI can render a dropdown without
guessing.

When ``ID_Name_Match`` flips off ``Pending``, ``AML_Check_Date`` is
auto-stamped today and ``AML_Checked_By`` records the acting agent — that
captures the "who did the AML review and when" trail required by the Money
Laundering Regulations 2017.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import Agent, require_agent
from app.core.logger import get_logger
from app.db import supabase_client as at

logger = get_logger(__name__)

router = APIRouter(prefix="/api/landlords", tags=["landlords"])


# Allowlisted Landlords columns the agent can edit from the UI. Same shape
# as properties.py:PATCHABLE_FLAGS plus ``single_select`` with options.
PATCHABLE_LANDLORD_FLAGS: dict[str, dict[str, Any]] = {
    # With Airtable gone this is the canonical editor for landlord records, so
    # it covers identity / contact / banking / residency, not just AML flags.
    # --- identity & contact ---
    "Full Name":      {"type": "text", "label": "Full name"},
    "Email Address":  {"type": "text", "label": "Email"},
    "Mobile Number":  {"type": "text", "label": "Mobile"},
    "Full Address":   {"type": "text", "label": "Address"},
    "Post Code":      {"type": "text", "label": "Postcode"},
    "Individual or Company": {
        "type": "single_select", "label": "Individual or company",
        "options": ["Individual", "Company"],
    },
    "Company Name":       {"type": "text", "label": "Company name"},
    "Director Name":      {"type": "text", "label": "Director name"},
    "Company Reg Number": {"type": "text", "label": "Company reg number"},
    # --- residency / NRL ---
    "UK_Resident_Status": {
        "type": "single_select", "label": "Residency",
        "options": ["Resident", "Non-resident"],
    },
    "NRL_Approval_Number": {
        "type": "text",
        "label": "NRL approval number (HMRC)",
    },
    # --- banking (disbursements) ---
    "Bank Name":      {"type": "text", "label": "Bank name"},
    "Sort Code":      {"type": "text", "label": "Sort code"},
    "Account Name":   {"type": "text", "label": "Account name"},
    "Account Number": {"type": "text", "label": "Account number"},
    # --- AML review ---
    "Verification Status": {
        "type": "single_select",
        "label": "Verification status",
        "options": ["Pending Review", "Approved", "Rejected"],
        # Stored values stay the same; these are richer labels the UI shows so
        # the agent knows what each choice means (UAT feedback #5).
        "option_labels": {
            "Pending Review": "Pending review - AML checks not yet complete",
            "Approved": "Approved - identity & AML checks passed, cleared to proceed",
            "Rejected": "Rejected - checks failed or documents insufficient",
        },
    },
    "ID_Name_Match": {
        "type": "single_select",
        "label": "ID name match (AML review)",
        "options": ["Pending", "Confirmed", "Mismatch"],
    },
    # Note: AML_Check_Date is auto-stamped when ID_Name_Match flips off
    # "Pending"; not exposed as a directly-editable field on its own.
}


@router.get("/flags-catalog")
def flags_catalog(_: Agent = Depends(require_agent)) -> dict[str, Any]:
    return {
        "fields": [
            {"name": name, **meta}
            for name, meta in PATCHABLE_LANDLORD_FLAGS.items()
        ],
    }


@router.patch("/{landlord_id}/flags")
def patch_flags(
    landlord_id: str,
    body: dict[str, Any],
    agent: Agent = Depends(require_agent),
) -> dict[str, Any]:
    """Apply a partial update to allow-listed Landlord fields."""
    if not isinstance(body, dict) or not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "body must be a non-empty object")

    unknown = [k for k in body if k not in PATCHABLE_LANDLORD_FLAGS]
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Field(s) not patchable: {', '.join(unknown)}",
        )

    payload: dict[str, Any] = {}
    today = date.today().isoformat()

    for k, raw in body.items():
        meta = PATCHABLE_LANDLORD_FLAGS[k]
        t = meta["type"]
        if t == "single_select":
            val = (raw or "").strip()
            if val and val not in meta["options"]:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"{k}: {val!r} not in allowed options {meta['options']}",
                )
            payload[k] = val or None
            # Side-effect: stamp the AML audit trail when an AML decision lands.
            if k == "ID_Name_Match" and val in ("Confirmed", "Mismatch"):
                payload["AML_Check_Date"] = today
                payload["AML_Checked_By"] = agent.email
        elif t == "text":
            payload[k] = "" if raw is None else str(raw)
        elif t == "bool":
            payload[k] = bool(raw)
        else:  # pragma: no cover — registry is internal
            raise HTTPException(500, f"Unknown field type {t!r} for {k}")

    try:
        at.update(at.TableNames.LANDLORDS, landlord_id, payload)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Landlord not found")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Update rejected: {e}")

    fresh = at.get(at.TableNames.LANDLORDS, landlord_id).get("fields", {})
    return {
        "landlord_id": landlord_id,
        "updated": {k: fresh.get(k) for k in payload},
    }
