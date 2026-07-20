"""Referencing — Stage 5 UI backing for Paragon checks.

Three endpoints replace the "go edit Airtable manually" workflow:

  GET  /api/properties/{property_id}/referencing
       Current referencing state across all tenants on the property.

  POST /api/properties/{property_id}/referencing/instruct
       (Re-)instruct Paragon for every tenant that doesn't already have a
       reference number on file. Idempotent — a tenant already referenced is
       skipped. Stores the returned ref on ``Tenants.Referencing_Paragon_Ref``.

  POST /api/properties/{property_id}/referencing/outcome
       Record the result (Pass | Conditional | Fail) for one tenant + the
       landlord approval flag. Sets ``Tenants.Referencing_Status`` and, when
       the whole tenancy has resulted, flips ``Properties.Referencing_Recorded``
       so the Stage 5→6 gate can pass.

The Paragon client runs in mock mode automatically when ``PARAGON_TOKEN`` is
unset, so the UI works end-to-end without real Paragon credentials.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import Agent, require_agent
from app.core.logger import get_logger
from app.core.paragon_client import instruct_paragon
from app.db import supabase_client as at

router = APIRouter(prefix="/api/properties", tags=["referencing"])
logger = get_logger(__name__)


ReferencingOutcome = Literal["Pass", "Conditional", "Fail", "Pending"]


def _load_tenants(property_id: str) -> tuple[dict, list[dict]]:
    """Fetch property + every tenant linked to it.

    Returns (property_fields, [tenant_fields_with_id]).
    """
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    pfields = prop.get("fields", {})
    tenants: list[dict] = []
    for tid in pfields.get("Tenant") or []:
        try:
            tf = at.get(at.TableNames.TENANTS, tid).get("fields", {})
            tenants.append({"id": tid, **tf})
        except Exception:
            pass
    return pfields, tenants


@router.get("/{property_id}/referencing")
def referencing_state(
    property_id: str,
    _: Agent = Depends(require_agent),
) -> dict:
    pfields, tenants = _load_tenants(property_id)
    # Tenant-level "referencing recorded" — true once we have a Pass / Fail /
    # Conditional outcome on file for that tenant.
    def _ref_recorded(t: dict) -> bool:
        return bool(t.get("Referencing_Recorded")) or (t.get("Referencing_Status") or "Pending") != "Pending"

    # Landlord approval is a *property-level* concept — it's the existing
    # `LL_Offer_Accepted` checkbox on Properties (the landlord either accepts
    # the offer + the references, or they don't). The per-tenant
    # `Landlord_Approval_Received` on Tenants is no longer used.
    ll_approved_property = bool(pfields.get("LL_Offer_Accepted"))

    return {
        "property_id": property_id,
        "tenants": [
            {
                "id": t["id"],
                "name": t.get("Name"),
                "email": t.get("Tenant Email"),
                "paragon_reference": t.get("Referencing_Paragon_Ref"),
                "outcome": t.get("Referencing_Status") or "Pending",
                "referencing_recorded": _ref_recorded(t),
                "is_student": bool(t.get("Is_Student")),
                "has_guarantor": bool(t.get("Guarantor_Name")),
            }
            for t in tenants
        ],
        # property-level rollups
        "landlord_approval_received": ll_approved_property,
        "referencing_recorded": bool(tenants) and all(_ref_recorded(t) for t in tenants),
        "monthly_rent": (tenants[0].get("Amount") if tenants else None),
        "guarantor_name": (tenants[0].get("Guarantor_Name") if tenants else None),
    }


@router.post("/{property_id}/referencing/instruct", status_code=status.HTTP_201_CREATED)
async def instruct_referencing(
    property_id: str,
    _: Agent = Depends(require_agent),
) -> dict:
    """Instruct Paragon for every tenant that doesn't already have a ref number."""
    # Stage gate — referencing is a Stage 5 action. Block earlier so the agent
    # can't accidentally instruct Paragon before an offer is recorded.
    from app.routers.forms import _require_stage  # local import — avoid cycles
    _require_stage(property_id, required=5, action="Instruct referencing")

    pfields, tenants = _load_tenants(property_id)
    if not tenants:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No tenants linked to this property")
    instructed: list[dict] = []
    for t in tenants:
        if t.get("Referencing_Paragon_Ref"):
            continue
        try:
            resp = await instruct_paragon(
                tenant_full_name=t.get("Name") or "Tenant",
                tenant_email=t.get("Tenant Email") or "",
                property_address=pfields.get("Address", ""),
                monthly_rent=float(t.get("Amount") or 0),
                guarantor_required=bool(t.get("Guarantor_Name")),
            )
            ref = resp.get("reference_number")
            if ref:
                at.update(at.TableNames.TENANTS, t["id"], {"Referencing_Paragon_Ref": ref})
                instructed.append({"tenant_id": t["id"], "reference": ref, "mock": bool(resp.get("_mock"))})
        except Exception as e:  # noqa: BLE001
            logger.warning("referencing.instruct_failed tenant=%s err=%s", t["id"], e)
            instructed.append({"tenant_id": t["id"], "error": str(e)})
    return {"property_id": property_id, "instructed": instructed}


class OutcomeRequest(BaseModel):
    tenant_id: Optional[str] = None
    outcome: Optional[ReferencingOutcome] = None
    landlord_approval_received: Optional[bool] = None
    """Set to true when the landlord confirms they accept the reference outcome."""


@router.post("/{property_id}/referencing/outcome")
def record_outcome(
    property_id: str,
    body: OutcomeRequest,
    _: Agent = Depends(require_agent),
) -> dict:
    """Patch one tenant's referencing outcome and / or the landlord's
    offer-acceptance flag.

    - ``tenant_id`` + ``outcome`` → updates that tenant's `Referencing_Status`
      (and `Referencing_Recorded` if the field exists on the Tenants table).
    - ``landlord_approval_received`` → writes the property-level
      `LL_Offer_Accepted` checkbox. (Consolidated 2026-05-16 — previously we
      wrote a separate Tenants.Landlord_Approval_Received but it duplicates
      the existing Property field.)
    """
    pfields, tenants = _load_tenants(property_id)
    if not tenants:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No tenants linked")

    warnings: list[str] = []

    # ---- Per-tenant referencing outcome --------------------------------
    if body.tenant_id and body.outcome:
        t = next((x for x in tenants if x["id"] == body.tenant_id), None)
        if not t:
            raise HTTPException(404, f"Tenant {body.tenant_id} not on this property")
        try:
            at.update(at.TableNames.TENANTS, body.tenant_id, {
                "Referencing_Status": body.outcome,
                "Referencing_Recorded": True,
            })
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "UNKNOWN_FIELD_NAME" in msg and "Referencing_Recorded" in msg:
                # Field not present — write just the status and warn.
                at.update(at.TableNames.TENANTS, body.tenant_id, {"Referencing_Status": body.outcome})
                warnings.append("Tenants.Referencing_Recorded checkbox not found — only the Status was saved.")
            else:
                raise

    # ---- Landlord approval → Property.LL_Offer_Accepted ----------------
    if body.landlord_approval_received is not None:
        try:
            at.update(at.TableNames.PROPERTIES, property_id, {
                "LL_Offer_Accepted": body.landlord_approval_received,
            })
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Could not update LL_Offer_Accepted: {e}")
            logger.warning("referencing.ll_offer_update_failed err=%s", e)

    # ---- Rollups -------------------------------------------------------
    refetched: list[dict] = []
    for t in tenants:
        try:
            refetched.append(at.get(at.TableNames.TENANTS, t["id"]).get("fields", {}))
        except Exception:
            refetched.append(t)
    all_resolved = all((rf.get("Referencing_Status") or "Pending") != "Pending" for rf in refetched)

    # Re-fetch property to pick up the LL_Offer_Accepted write.
    try:
        ll_approved = bool(at.get(at.TableNames.PROPERTIES, property_id)
                            .get("fields", {}).get("LL_Offer_Accepted"))
    except Exception:
        ll_approved = bool(pfields.get("LL_Offer_Accepted"))

    return {
        "property_id": property_id,
        "referencing_recorded": all_resolved,
        "landlord_approval_received": ll_approved,
        "warnings": warnings,
    }
