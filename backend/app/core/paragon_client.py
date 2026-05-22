"""Paragon referencing API client.

Real Paragon offers a JSON API for instructing a reference and then receiving
the outcome via webhook. While the real integration credentials are being
sourced, this module operates in **mock mode** by default — it produces a
deterministic-looking reference number, logs the instruction, and returns
without making a network call. Replace the body of ``instruct_paragon`` with
a real ``httpx`` POST once the API key arrives.

Configuration: drop ``PARAGON_TOKEN`` and ``PARAGON_URL`` into ``.env``.
Mock mode auto-activates whenever ``PARAGON_TOKEN`` is missing or set to the
``REPLACE_ME`` placeholder, mirroring the DocuSeal client convention.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from app.core.logger import get_logger

logger = get_logger(__name__)


# In-memory ledger of mock instructions so the dev/test harness can simulate
# Paragon callback events. Keyed by reference number.
MOCK_PARAGON_INSTRUCTIONS: dict[str, dict[str, Any]] = {}


def _mock_mode_active() -> bool:
    # Settings imported lazily so this module stays importable in tests that
    # haven't set up the env yet.
    from app.config import settings
    tok = (getattr(settings, "paragon_token", "") or "").strip()
    return (not tok) or tok.upper().startswith("REPLACE_ME")


async def instruct_paragon(
    *,
    tenant_full_name: str,
    tenant_email: str,
    property_address: str,
    monthly_rent: float,
    guarantor_required: bool = False,
    include_right_to_rent: bool = True,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Instruct a Paragon referencing run for one tenant.

    Returns a dict shaped like Paragon's real response so callers don't have
    to switch on mock vs. real:

        {
            "reference_number": "PRG-xxxxxxxx",
            "status": "instructed",
            "instructed_at": ISO timestamp,
            "_mock": bool,
        }
    """
    if _mock_mode_active():
        ref = f"PRG-MOCK-{secrets.token_hex(4).upper()}"
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "reference_number": ref,
            "status": "instructed",
            "instructed_at": now,
            "tenant_full_name": tenant_full_name,
            "tenant_email": tenant_email,
            "property_address": property_address,
            "monthly_rent": monthly_rent,
            "guarantor_required": guarantor_required,
            "include_right_to_rent": include_right_to_rent,
            "metadata": metadata or {},
            "_mock": True,
        }
        MOCK_PARAGON_INSTRUCTIONS[ref] = record
        logger.info(
            "paragon.mock.instructed ref=%s tenant=%r email=%s (no real PARAGON_TOKEN)",
            ref, tenant_full_name, tenant_email,
        )
        return {
            "reference_number": ref,
            "status": "instructed",
            "instructed_at": now,
            "_mock": True,
        }

    # Real Paragon call would go here. Once we have credentials:
    #   from app.config import settings
    #   import httpx
    #   async with httpx.AsyncClient(timeout=30) as client:
    #       r = await client.post(
    #           f"{settings.paragon_url}/api/instructions",
    #           headers={"Authorization": f"Bearer {settings.paragon_token}"},
    #           json={...},
    #       )
    #       r.raise_for_status()
    #       return r.json()
    raise RuntimeError("Paragon real-mode not implemented yet — token is set but client body is a stub")


def mock_paragon_outcome(reference_number: str, outcome: str = "Pass") -> dict[str, Any]:
    """Build a Paragon-shaped result payload for a previously mocked instruction.

    `outcome` is one of: Pass | Conditional | Fail. The test harness can call
    this and pass the result into the tenant flow / referencing webhook.
    """
    inst = MOCK_PARAGON_INSTRUCTIONS.get(reference_number)
    if not inst:
        raise KeyError(f"Unknown mock Paragon reference: {reference_number}")
    return {
        "reference_number": reference_number,
        "tenant_full_name": inst["tenant_full_name"],
        "outcome": outcome,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "_mock": True,
    }
