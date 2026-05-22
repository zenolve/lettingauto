"""Auth primitives.

Two flavours of token coexist:

1. **Agent JWT** — issued by `/auth/login`, carried in `Authorization: Bearer`.
   Used to gate all `/api/agent/*` endpoints.
2. **Form access token** — short-lived, scoped to a specific property + form +
   landlord email. Embedded in URLs sent to landlords (`?token=...`). Replaces
   the implicit Tally `?id=X&email=Y` pattern with something signed.

The bootstrap agent account is stored in-process: a single record loaded from
env at startup. For production a real `Agents` Airtable table can be added —
the lookup is abstracted behind `get_agent_by_email`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# In-process agent registry (bootstrap user; extend to Airtable if needed).
# ---------------------------------------------------------------------------
class Agent(BaseModel):
    email: str
    hashed_password: str
    name: str = "Palace Gate Agent"


_AGENTS: dict[str, Agent] = {}


def _ensure_bootstrap_agent() -> None:
    email = settings.agent_bootstrap_email.lower()
    if email not in _AGENTS:
        _AGENTS[email] = Agent(
            email=email,
            hashed_password=_pwd.hash(settings.agent_bootstrap_password),
        )


_ensure_bootstrap_agent()


def get_agent_by_email(email: str) -> Optional[Agent]:
    return _AGENTS.get(email.lower())


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Agent JWT
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


def require_agent(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Agent:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    payload = decode_token(creds.credentials)
    if payload.get("type") != "agent":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not an agent token")
    agent = get_agent_by_email(payload["sub"])
    if not agent:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown agent")
    return agent


# ---------------------------------------------------------------------------
# Form access tokens (sent to landlords/tenants via email).
# ---------------------------------------------------------------------------
class FormTokenPayload(BaseModel):
    property_id: str            # Airtable record ID (rec...)
    form: str                   # e.g. "landlord_admin", "landlord_verification"
    email: Optional[str] = None
    landlord_id: Optional[str] = None


def create_form_token(payload: FormTokenPayload, *, ttl_days: int = 30) -> str:
    body = {
        **payload.model_dump(),
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
