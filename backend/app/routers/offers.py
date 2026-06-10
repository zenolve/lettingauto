"""Offer lifecycle endpoints (Gap 5 / Gap 1).

  GET   /api/properties/{property_id}/offers   list offers for a property
  POST  /api/offers/{offer_id}/accept          accept (links tenants, supersedes rivals)
  POST  /api/offers/{offer_id}/reject          landlord rejected
  POST  /api/offers/{offer_id}/withdraw        tenant withdrew (Gap 1)

Accept/close logic lives in ``app.services.offers`` so the DocuSign webhook
can reuse it.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import Agent, require_agent
from app.db import supabase_client as at
from app.services import offers as offers_svc

router = APIRouter(tags=["offers"])


def _to_summary(rec: dict) -> dict:
    f = rec.get("fields", {})
    return {
        "id": rec["id"],
        "name": f.get("Name"),
        "status": f.get("Status"),
        "tenant_ids": f.get("Tenants") or [],
        "offered_rent": f.get("Offered Rent"),
        "rent_frequency": f.get("Rent Frequency"),
        "deposit": f.get("Deposit"),
        "holding_deposit": f.get("Holding Deposit"),
        "start_date": f.get("Start Date"),
        "end_date": f.get("End Date"),
        "tenancy_term": f.get("Tenancy Term"),
        "holding_deposit_deadline": f.get("Holding Deposit Deadline"),
        "created_at": f.get("Created At"),
        "closed_at": f.get("Closed At"),
        "close_reason": f.get("Close Reason"),
        "created_by": f.get("Created By"),
    }


@router.get("/api/properties/{property_id}/offers")
def list_offers(property_id: str, _: Agent = Depends(require_agent)) -> dict[str, Any]:
    rows = offers_svc.offers_for_property(property_id)
    return {"property_id": property_id, "offers": [_to_summary(r) for r in rows]}


def _load_offer_or_404(offer_id: str) -> dict:
    try:
        return at.get(at.TableNames.OFFERS, offer_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")


@router.post("/api/offers/{offer_id}/accept")
async def accept(offer_id: str, _: Agent = Depends(require_agent)) -> dict[str, Any]:
    of = _load_offer_or_404(offer_id).get("fields", {})
    if of.get("Status") not in ("Pending", None):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only a Pending offer can be accepted (this one is {of.get('Status')}).",
        )
    return await offers_svc.accept_offer(offer_id, source="agent")


class CloseBody(BaseModel):
    reason: Optional[str] = None


@router.post("/api/offers/{offer_id}/reject")
async def reject(offer_id: str, body: CloseBody | None = None,
                 _: Agent = Depends(require_agent)) -> dict[str, Any]:
    _load_offer_or_404(offer_id)
    return await offers_svc.close_offer(
        offer_id, status="Rejected_By_Landlord",
        reason=(body.reason if body else None), source="agent",
    )


@router.post("/api/offers/{offer_id}/withdraw")
async def withdraw(offer_id: str, body: CloseBody | None = None,
                   _: Agent = Depends(require_agent)) -> dict[str, Any]:
    _load_offer_or_404(offer_id)
    return await offers_svc.close_offer(
        offer_id, status="Withdrawn_By_Tenant",
        reason=(body.reason if body else None), source="agent",
    )
