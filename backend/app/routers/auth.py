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
    agent = get_agent_by_email(body.email)
    if not agent or not verify_password(body.password, agent.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return LoginResponse(token=create_agent_token(agent.email), email=agent.email, name=agent.name)


@router.get("/me")
def me(agent: Agent = Depends(require_agent)) -> dict:
    return {"email": agent.email, "name": agent.name}


@router.get("/form-token")
def inspect_form_token(token: str, form: str | None = None) -> dict:
    """Public endpoint used by the React form pages to confirm the URL token."""
    payload = decode_form_token(token, expected_form=form)
    return payload.model_dump()
