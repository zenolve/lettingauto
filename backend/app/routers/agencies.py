"""Agency onboarding + self-service.

  POST  /api/agencies/register             Create an agency for the signed-in
                                           Supabase user (becomes its owner)
  GET   /api/agencies/me                   Agency profile + membership + billing
  PATCH /api/agencies/me                   Update profile / branding / onboarding
  POST  /api/agencies/me/billing/setup-checkout   Stripe Checkout (add a card)
  POST  /api/agencies/me/billing/sync      Re-sync the live-tenancy quantity

Registration is the only endpoint that accepts a Supabase user WITHOUT a
membership; everything else runs through ``require_agent`` (which also scopes
the db layer to the caller's agency).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.core.auth import Agent, SupabaseUser, require_agent, require_supabase_user
from app.core.logger import get_logger
from app.db import supabase_client as at
from app.services import billing

router = APIRouter(prefix="/api/agencies", tags=["agencies"])
logger = get_logger(__name__)


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:50] or "agency"


class RegisterBody(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    office_address: Optional[str] = None
    website: Optional[str] = None


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_agency(body: RegisterBody, user: SupabaseUser = Depends(require_supabase_user)) -> dict[str, Any]:
    """Create an agency owned by the signed-in Supabase user."""
    existing = at.find_first(at.TableNames.AGENCY_USERS, at.eq("user_id", user.user_id))
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This account already belongs to an agency.",
        )

    slug = _slugify(body.name)
    if at.find_first(at.TableNames.AGENCIES, at.eq("slug", slug)):
        slug = f"{slug}-{user.user_id[:8]}"

    agency = at.create(at.TableNames.AGENCIES, {
        "name": body.name.strip(),
        "slug": slug,
        "email": body.email or user.email,
        "phone": body.phone,
        "office_address": body.office_address,
        "website": body.website,
        "billing_email": body.email or user.email,
    })
    at.create(at.TableNames.AGENCY_USERS, {
        "agency_id": agency["id"],
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.name,
        "role": "owner",
    })

    # Stripe customer is best-effort here; created lazily later if this fails.
    if billing.billing_enabled():
        try:
            billing.ensure_customer(agency["id"])
        except Exception as e:  # noqa: BLE001
            logger.warning("agencies.register.stripe_customer_failed err=%s", e)

    logger.info("agencies.registered id=%s name=%r owner=%s", agency["id"], body.name, user.email)
    return {"agency_id": agency["id"], "name": body.name, "slug": slug, "role": "owner"}


def _me_payload(agent: Agent) -> dict[str, Any]:
    agency = at.get(at.TableNames.AGENCIES, agent.agency_id)
    f = agency.get("fields", {})
    return {
        "agency_id": agency["id"],
        "name": f.get("name"),
        "slug": f.get("slug"),
        "email": f.get("email"),
        "phone": f.get("phone"),
        "office_address": f.get("office_address"),
        "website": f.get("website"),
        "logo_url": f.get("logo_url"),
        "brand_navy": f.get("brand_navy"),
        "brand_gold": f.get("brand_gold"),
        "onboarding_completed": bool(f.get("onboarding_completed")),
        "membership": {"email": agent.email, "name": agent.name, "role": agent.role},
        "billing": billing.billing_summary(agency["id"]),
    }


@router.get("/me")
def get_my_agency(agent: Agent = Depends(require_agent)) -> dict[str, Any]:
    if not agent.agency_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "no_agency"})
    return _me_payload(agent)


# Allowlisted, owner/admin-editable agency fields.
_PATCHABLE = {
    "name", "email", "phone", "office_address", "website", "logo_url",
    "brand_navy", "brand_gold", "billing_email", "onboarding_completed",
}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@router.patch("/me")
def patch_my_agency(body: dict[str, Any], agent: Agent = Depends(require_agent)) -> dict[str, Any]:
    if agent.role not in ("owner", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners/admins can edit the agency")
    unknown = [k for k in body if k not in _PATCHABLE]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Field(s) not editable: {', '.join(unknown)}")

    payload: dict[str, Any] = {}
    for k, v in body.items():
        if k == "onboarding_completed":
            payload[k] = bool(v)
        elif k in ("brand_navy", "brand_gold"):
            v = (v or "").strip()
            if v and not _HEX.match(v):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{k} must be a #RRGGBB colour")
            payload[k] = v or None
        elif k == "name":
            v = (v or "").strip()
            if len(v) < 2:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "name too short")
            payload[k] = v
        else:
            payload[k] = (str(v).strip() or None) if v is not None else None

    at.update(at.TableNames.AGENCIES, agent.agency_id, payload)
    return _me_payload(agent)


@router.post("/me/billing/setup-checkout", status_code=status.HTTP_201_CREATED)
def billing_setup_checkout(agent: Agent = Depends(require_agent)) -> dict[str, Any]:
    if agent.role not in ("owner", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners/admins manage billing")
    try:
        url = billing.create_setup_checkout(agent.agency_id)
    except billing.BillingError as e:
        code = status.HTTP_501_NOT_IMPLEMENTED if e.code == "billing_disabled" else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(code, str(e))
    return {"checkout_url": url}


@router.post("/me/billing/sync")
def billing_sync(agent: Agent = Depends(require_agent)) -> dict[str, Any]:
    count = billing.sync_live_tenancies(agent.agency_id)
    return {"live_tenancies": billing.count_live_tenancies(agent.agency_id),
            "synced": count is not None}
