"""Auth primitives — Supabase-auth'd agency users + scoped requests.

Three token flavours coexist:

1. **Supabase access token** (primary) — issued by Supabase Auth when an agent
   signs in on the frontend (email/password, Google, or Microsoft). Verified
   here with the project's JWT secret (HS256, audience ``authenticated``).
   The user's ``agency_users`` membership resolves the agency, and the db
   layer's agency scope is set for the request — every query is automatically
   confined to that agency's rows (see supabase_client.set_agency_scope).

2. **Legacy bootstrap agent JWT** — issued by ``/auth/login`` for the single
   env-configured account. Kept for local dev / smoke tests; it provisions and
   scopes to a "Bootstrap Agency". Disable with ``ALLOW_BOOTSTRAP_LOGIN=false``
   in production.

3. **Form access token** — short-lived, scoped to a specific property + form +
   landlord email. Embedded in URLs sent to landlords (``?token=...``). It
   carries the agency id so public form submissions write into the right
   agency.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


class Agent(BaseModel):
    """The authenticated agency user attached to a request."""
    email: str
    name: str = "Agent"
    agency_id: Optional[str] = None
    role: str = "owner"            # owner | admin | agent
    user_id: Optional[str] = None  # Supabase auth user id (None for bootstrap)


class SupabaseUser(BaseModel):
    """A verified Supabase identity that may not have an agency yet
    (used by the agency-registration endpoint)."""
    user_id: str
    email: str
    name: str = ""


# ---------------------------------------------------------------------------
# Bootstrap (legacy single-user) registry
# ---------------------------------------------------------------------------
class _BootstrapAgent(BaseModel):
    email: str
    hashed_password: str
    name: str = "Bootstrap Agent"


_AGENTS: dict[str, _BootstrapAgent] = {}
_BOOTSTRAP_AGENCY_NAME = "Bootstrap Agency"


def _ensure_bootstrap_agent() -> None:
    email = settings.agent_bootstrap_email.lower()
    if email not in _AGENTS:
        _AGENTS[email] = _BootstrapAgent(
            email=email,
            hashed_password=_pwd.hash(settings.agent_bootstrap_password),
        )


_ensure_bootstrap_agent()


def get_agent_by_email(email: str) -> Optional[_BootstrapAgent]:
    return _AGENTS.get(email.lower())


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def ensure_bootstrap_agency() -> str:
    """Get-or-create the dev/bootstrap agency; returns its id."""
    from app.db import supabase_client as at  # local — avoid import cycle

    existing = at.find_first(at.TableNames.AGENCIES, at.eq("slug", "bootstrap"))
    if existing:
        return existing["id"]
    rec = at.create(at.TableNames.AGENCIES, {
        "name": _BOOTSTRAP_AGENCY_NAME,
        "slug": "bootstrap",
        "email": settings.agent_bootstrap_email,
        "onboarding_completed": True,
    })
    logger.info("auth.bootstrap_agency_created id=%s", rec["id"])
    return rec["id"]


# ---------------------------------------------------------------------------
# Legacy agent JWT (bootstrap login)
# ---------------------------------------------------------------------------
def create_agent_token(email: str) -> str:
    payload = {
        "sub": email.lower(),
        "type": "agent",
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")


# ---------------------------------------------------------------------------
# Supabase access-token verification
# ---------------------------------------------------------------------------
def _decode_supabase_token(token: str) -> Optional[dict]:
    """Return Supabase JWT claims, or None if this isn't a Supabase token.

    Raises 401 only when the token IS Supabase-shaped but fails verification.
    """
    if not settings.supabase_jwt_secret:
        return None
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError:
        return None


def _supabase_user_from_claims(claims: dict) -> SupabaseUser:
    meta = claims.get("user_metadata") or {}
    return SupabaseUser(
        user_id=claims.get("sub") or "",
        email=(claims.get("email") or meta.get("email") or "").lower(),
        name=meta.get("full_name") or meta.get("name") or "",
    )


def _credentials_token(creds: HTTPAuthorizationCredentials | None) -> str:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return creds.credentials


async def require_supabase_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> SupabaseUser:
    """A verified Supabase identity — membership NOT required.

    Used by ``POST /api/agencies/register`` (the user exists in Supabase Auth
    but has no agency yet).
    """
    token = _credentials_token(creds)
    claims = _decode_supabase_token(token)
    if not claims:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "A Supabase session token is required (configure SUPABASE_JWT_SECRET).",
        )
    user = _supabase_user_from_claims(claims)
    if not user.user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token has no subject")
    return user


def _resolve_membership(user: SupabaseUser):
    from app.db import supabase_client as at  # local — avoid import cycle

    membership = at.find_first(at.TableNames.AGENCY_USERS, at.eq("user_id", user.user_id))
    if not membership:
        # 403 with a machine-readable code: the frontend routes this to the
        # agency-registration screen.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "no_agency", "message": "This account has no agency yet — register one."},
        )
    mf = membership.get("fields", {})
    return Agent(
        email=user.email or mf.get("email", ""),
        name=user.name or mf.get("full_name") or "Agent",
        agency_id=str(mf.get("agency_id")),
        role=mf.get("role", "agent"),
        user_id=user.user_id,
    )


async def require_agent(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AsyncIterator[Agent]:
    """Authenticate the request and scope the db layer to the caller's agency.

    Accepts a Supabase access token (primary) or, when enabled, the legacy
    bootstrap agent JWT. The agency scope is reset when the request finishes.
    """
    from app.db import supabase_client as at  # local — avoid import cycle

    token = _credentials_token(creds)

    agent: Agent | None = None
    claims = _decode_supabase_token(token)
    if claims:
        agent = _resolve_membership(_supabase_user_from_claims(claims))
    else:
        payload = decode_token(token)  # raises 401 on garbage
        if payload.get("type") != "agent":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not an agent token")
        if not settings.allow_bootstrap_login:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bootstrap login is disabled")
        bootstrap = get_agent_by_email(payload["sub"])
        if not bootstrap:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown agent")
        agent = Agent(
            email=bootstrap.email,
            name=bootstrap.name,
            agency_id=ensure_bootstrap_agency(),
            role="owner",
        )

    scope_token = at.set_agency_scope(agent.agency_id)
    try:
        yield agent
    finally:
        at.reset_agency_scope(scope_token)


# ---------------------------------------------------------------------------
# Form access tokens (sent to landlords/tenants via email).
# ---------------------------------------------------------------------------
class FormTokenPayload(BaseModel):
    property_id: str            # record id (uuid)
    form: str                   # e.g. "landlord_admin", "landlord_verification"
    email: Optional[str] = None
    landlord_id: Optional[str] = None
    agency_id: Optional[str] = None  # carried so public submissions stay scoped


def create_form_token(payload: FormTokenPayload, *, ttl_days: int = 30) -> str:
    body = payload.model_dump()
    if not body.get("agency_id"):
        # Stamp the current scope so the public form writes land in the
        # right agency even though the landlord is unauthenticated.
        from app.db import supabase_client as at  # local import
        body["agency_id"] = at.current_agency_id()
    body |= {
        "type": "form",
        "exp": datetime.now(timezone.utc) + timedelta(days=ttl_days),
    }
    return jwt.encode(body, settings.jwt_secret, algorithm="HS256")


def decode_form_token(token: str, *, expected_form: str | None = None) -> FormTokenPayload:
    payload = decode_token(token)
    if payload.get("type") != "form":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a form token")
    if expected_form and payload.get("form") != expected_form:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token form mismatch")
    return FormTokenPayload(**{k: payload.get(k) for k in FormTokenPayload.model_fields})
