"""Auth endpoints: agent login + form token introspection."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.core.auth import (
    Agent,
    create_agent_token,
    decode_form_token,
    get_agent_by_email,
    require_agent,
    verify_password,
)
from app.db import supabase_client as at

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    token: str
    email: str
    name: str


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    """Legacy bootstrap login (single env-configured account, dev only).

    Production sign-in is Supabase Auth on the frontend (email / Google /
    Microsoft) — the backend just verifies those tokens in require_agent.
    """
    from app.config import settings  # noqa: PLC0415
    if not settings.allow_bootstrap_login:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Password login is disabled — sign in with Supabase Auth.")
    agent = get_agent_by_email(body.email)
    if not agent or not verify_password(body.password, agent.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return LoginResponse(token=create_agent_token(agent.email), email=agent.email, name=agent.name)


@router.get("/me")
def me(agent: Agent = Depends(require_agent)) -> dict:
    return {"email": agent.email, "name": agent.name,
            "agency_id": agent.agency_id, "role": agent.role}


@router.get("/form-token")
def inspect_form_token(token: str, form: str | None = None) -> dict:
    """Public endpoint used by the React form pages to confirm the URL token.

    When the token carries a ``landlord_id`` we additionally dereference the
    Landlords record and surface ``landlord_full_name`` so the landlord-facing
    forms (PG_02 admin, PG_02b verification) can prefill name fields the
    agent already captured at take-on. Best-effort: if Airtable fails or the
    record was deleted we just return the bare token payload.
    """
    payload = decode_form_token(token, expected_form=form)
    # Fail fast on links that outlived their property (deleted after the email
    # went out) so the landlord sees a clear message on page load instead of a
    # 500 after filling in the whole form. Same 410 as the submit endpoints.
    if payload.property_id:
        from app.routers.forms import ensure_form_property_exists  # noqa: PLC0415
        ensure_form_property_exists(payload.property_id)
    out = payload.model_dump()
    # Surface the inviting agency's name so the public landlord forms address
    # the landlord as that agency (no platform branding leaks).
    if payload.agency_id:
        try:
            af = at.get(at.TableNames.AGENCIES, payload.agency_id).get("fields", {})
            out["agency_name"] = af.get("name")
        except Exception:
            pass
    if payload.landlord_id:
        try:
            landlord = at.get(at.TableNames.LANDLORDS, payload.landlord_id)
            lf = landlord.get("fields", {})
            out["landlord_full_name"] = lf.get("Full Name")
            # Wave B: surface the residency PG_02 captured so the verification
            # form can drive its visa-upload conditional without re-asking.
            out["residency"] = lf.get("UK_Resident_Status")
        except Exception:
            pass
    return out
