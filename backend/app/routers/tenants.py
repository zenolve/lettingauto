"""Tenant-level CRUD — the agent-facing editor for tenant records.

With Airtable gone there is no external UI for fixing entity data, so every
editable field is exposed here behind a typed allowlist (same pattern as
properties.py / landlords.py flags):

  GET    /api/tenants/fields-catalog    Editable fields + types for the UI
  GET    /api/tenants/{id}              One tenant record
  PATCH  /api/tenants/{id}              Partial update of allowlisted fields
  DELETE /api/tenants/{id}              Remove a tenant record

All access is agency-scoped by require_agent — a tenant id from another
agency 404s.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import Agent, require_agent
from app.core.logger import get_logger
from app.db import supabase_client as at

router = APIRouter(prefix="/api/tenants", tags=["tenants"])
logger = get_logger(__name__)


# Editable tenant fields. type ∈ text | email | date | number | int | bool |
# single_select (with options). Keys are the live field names the rest of the
# pipeline reads.
EDITABLE_TENANT_FIELDS: dict[str, dict[str, Any]] = {
    "Name":                    {"type": "text",   "label": "Full name"},
    "Tenant Email":            {"type": "email",  "label": "Email"},
    "Tenant Address":          {"type": "text",   "label": "Current address"},
    "Start Date":              {"type": "date",   "label": "Tenancy start"},
    "End Date":                {"type": "date",   "label": "Tenancy end"},
    "Tenancy Term":            {"type": "text",   "label": "Term"},
    "Amount":                  {"type": "number", "label": "Rent amount"},
    "Rent_Frequency":          {"type": "single_select", "label": "Rent frequency",
                                "options": ["Monthly", "Weekly"]},
    "Deposit Amount":          {"type": "number", "label": "Deposit"},
    "Holding_Deposit":         {"type": "number", "label": "Holding deposit"},
    "Rent_In_Advance_Months":  {"type": "int",    "label": "Rent in advance (months)"},
    "Break Clause":            {"type": "number", "label": "Break clause fee (£)"},
    "Renew":                   {"type": "text",   "label": "Renewal terms"},
    "Special Condition":       {"type": "text",   "label": "Special conditions"},
    "Guarantor_Name":          {"type": "text",   "label": "Guarantor name"},
    "Gurantor Address":        {"type": "text",   "label": "Guarantor address"},
    "Guarantor_Email":         {"type": "email",  "label": "Guarantor email"},
    "Is_Student":              {"type": "bool",   "label": "Student"},
    "Referencing_Status":      {"type": "single_select", "label": "Referencing status",
                                "options": ["Pending", "Pass", "Conditional", "Fail"]},
    "Referencing_Recorded":    {"type": "bool",   "label": "Referencing recorded"},
    "Referencing_Paragon_Ref": {"type": "text",   "label": "Paragon reference"},
    "TA_Signed":               {"type": "bool",   "label": "TA signed (this tenant)"},
    "RTR_Check_Type":          {"type": "single_select", "label": "Right-to-Rent check",
                                "options": ["Manual", "IDSP", "Share Code", "Paragon"]},
    "RTR_Check_Date":          {"type": "date",   "label": "RTR check date"},
    "RTR_Doc_Reference":       {"type": "text",   "label": "RTR document reference"},
    "Visa_Expiry_Date":        {"type": "date",   "label": "Visa expiry"},
}


def coerce_patch(allowlist: dict[str, dict[str, Any]], body: dict[str, Any]) -> dict[str, Any]:
    """Validate + coerce a partial-update body against a field allowlist.

    Shared by the tenant / landlord / property editors so all three behave
    identically (None or "" clears a field; types enforced server-side).
    """
    unknown = [k for k in body if k not in allowlist]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Field(s) not editable: {', '.join(unknown)}")
    payload: dict[str, Any] = {}
    for k, raw in body.items():
        meta = allowlist[k]
        t = meta["type"]
        if raw is None or raw == "":
            payload[k] = None
            continue
        if t == "bool":
            payload[k] = bool(raw)
        elif t == "int":
            try:
                payload[k] = int(raw)
            except (TypeError, ValueError):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{k}: expected an integer")
        elif t == "number":
            try:
                payload[k] = float(raw)
            except (TypeError, ValueError):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{k}: expected a number")
        elif t == "single_select":
            val = str(raw).strip()
            if val not in meta["options"]:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    f"{k}: {val!r} not in {meta['options']}")
            payload[k] = val
        elif t in ("text", "email", "date"):
            payload[k] = str(raw).strip()
        else:  # pragma: no cover — registry is internal
            raise HTTPException(500, f"Unknown field type {t!r} for {k}")
    return payload


@router.get("/fields-catalog")
def fields_catalog(_: Agent = Depends(require_agent)) -> dict[str, Any]:
    return {"fields": [{"name": n, **m} for n, m in EDITABLE_TENANT_FIELDS.items()]}


@router.get("/{tenant_id}")
def get_tenant(tenant_id: str, _: Agent = Depends(require_agent)) -> dict[str, Any]:
    try:
        rec = at.get(at.TableNames.TENANTS, tenant_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    return {"id": rec["id"], "fields": rec.get("fields", {})}


@router.patch("/{tenant_id}")
def patch_tenant(tenant_id: str, body: dict[str, Any], _: Agent = Depends(require_agent)) -> dict[str, Any]:
    if not isinstance(body, dict) or not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "body must be a non-empty object")
    payload = coerce_patch(EDITABLE_TENANT_FIELDS, body)
    try:
        at.update(at.TableNames.TENANTS, tenant_id, payload)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    fresh = at.get(at.TableNames.TENANTS, tenant_id).get("fields", {})
    return {"tenant_id": tenant_id, "updated": {k: fresh.get(k) for k in payload}}


@router.delete("/{tenant_id}")
def delete_tenant(tenant_id: str, _: Agent = Depends(require_agent)) -> dict[str, Any]:
    try:
        at.delete(at.TableNames.TENANTS, tenant_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    logger.info("tenant.deleted id=%s", tenant_id)
    return {"deleted": tenant_id}
