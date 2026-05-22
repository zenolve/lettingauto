"""DocuSeal API client.

Two integration modes are supported:

1. **Template-based** — push prefill values into an existing DocuSeal template
   and create a submission. Used for the legacy Offer Letter / Instruction
   Letter flow described in spec §7.1.
2. **PDF upload** — the new contract editor flow: we render the in-app HTML to
   PDF (WeasyPrint), then create a one-shot DocuSeal template + submission
   wrapping that PDF.

If `DOCUSEAL_TOKEN` is missing or still set to the `REPLACE_ME` placeholder, a
mock mode kicks in: the client synthesises a DocuSeal-shaped success response
locally so the rest of the workflow (PG_03 → PG_04 etc.) can run end-to-end
without a live DocuSeal instance. Mock submissions are also stamped into the
`MOCK_DOCUSEAL_SUBMISSIONS` registry so the test harness / scheduler can replay
a synthetic "signed" webhook against them.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


# In-memory ledger of mock submissions — keyed by submission id. Lets a dev
# helper replay PG_04 callbacks without a real DocuSeal instance.
MOCK_DOCUSEAL_SUBMISSIONS: dict[str, dict[str, Any]] = {}


def _mock_mode_active() -> bool:
    tok = (settings.docuseal_token or "").strip()
    return (not tok) or tok.upper().startswith("REPLACE_ME")


def _mock_submission(
    *,
    name: str,
    submitters: list[dict[str, Any]],
    template_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    submission_id = f"mock-{secrets.token_hex(8)}"
    now = datetime.now(timezone.utc).isoformat()
    mock_submitters: list[dict[str, Any]] = []
    for idx, s in enumerate(submitters):
        sid = f"{submission_id}-s{idx}"
        slug = secrets.token_urlsafe(12)
        mock_submitters.append({
            "id": sid,
            "submission_id": submission_id,
            "email": s.get("email"),
            "name": s.get("name"),
            "role": s.get("role"),
            "status": "pending",
            "slug": slug,
            "url": f"{settings.docuseal_url}/s/{slug}",
            "embed_src": f"{settings.docuseal_url}/s/{slug}",
            "sent_at": now,
        })
    response = {
        "id": submission_id,
        "status": "pending",
        "name": name,
        "template_id": template_id,
        "submitters": mock_submitters,
        "metadata": metadata or {},
        "created_at": now,
        "_mock": True,
    }
    MOCK_DOCUSEAL_SUBMISSIONS[submission_id] = response
    logger.info(
        "docuseal.mock.submission_created id=%s name=%r submitters=%d",
        submission_id, name, len(mock_submitters),
    )
    return response


def _headers() -> dict[str, str]:
    if not settings.docuseal_token:
        raise RuntimeError("DOCUSEAL_TOKEN is not configured")
    return {
        "X-Auth-Token": settings.docuseal_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ---------------------------------------------------------------------------
# Template-based submission (legacy flow used by PG_03 Offer handler).
# ---------------------------------------------------------------------------
async def create_template_submission(
    *,
    template_id: int,
    submitters: list[dict[str, Any]],
    prefill_fields: dict[str, Any] | None = None,
    send_email: bool = True,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _mock_mode_active():
        logger.warning(
            "docuseal.mock.template_submission template_id=%s (no real DOCUSEAL_TOKEN)",
            template_id,
        )
        return _mock_submission(
            name=f"template-{template_id}",
            submitters=submitters,
            template_id=template_id,
            metadata=metadata,
        )

    payload: dict[str, Any] = {
        "template_id": template_id,
        "send_email": send_email,
        "submitters": submitters,
    }
    if prefill_fields:
        payload["fields"] = [
            {"name": k, "default_value": str(v) if v is not None else "", "readonly": True}
            for k, v in prefill_fields.items()
        ]
    if metadata:
        payload["metadata"] = metadata

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{settings.docuseal_url}/api/submissions",
            headers=_headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# PDF upload (new contract editor flow).
# ---------------------------------------------------------------------------
async def create_pdf_submission(
    *,
    name: str,
    pdf_bytes: bytes,
    submitters: list[dict[str, Any]],
    send_email: bool = True,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Upload a PDF and create a submission against it in a single call.

    Uses DocuSeal's `documents` payload form which accepts base64-encoded files.
    """
    if _mock_mode_active():
        logger.warning(
            "docuseal.mock.pdf_submission name=%r bytes=%d (no real DOCUSEAL_TOKEN)",
            name, len(pdf_bytes),
        )
        return _mock_submission(name=name, submitters=submitters, metadata=metadata)

    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    payload: dict[str, Any] = {
        "name": name,
        "send_email": send_email,
        "submitters": submitters,
        "documents": [{"name": f"{name}.pdf", "file": b64}],
    }
    if metadata:
        payload["metadata"] = metadata

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{settings.docuseal_url}/api/submissions",
            headers=_headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Mock-mode helper for replaying a "signed" callback locally.
# ---------------------------------------------------------------------------
def mock_signed_event(submission_id: str, template_name: str) -> dict[str, Any]:
    """Build a DocuSeal-shaped `submission.completed` payload for a mock id.

    The dev/test helper calls this and POSTs the result to
    `/webhook/docuseal-signed` to drive PG_04 without a real DocuSeal instance.
    """
    sub = MOCK_DOCUSEAL_SUBMISSIONS.get(submission_id)
    if not sub:
        raise KeyError(f"Unknown mock submission id: {submission_id}")
    now = datetime.now(timezone.utc).isoformat()
    return {
        "event_type": "submission.completed",
        "data": {
            "submission_id": submission_id,
            "template": {"name": template_name},
            "metadata": sub.get("metadata") or {},
            "submitters": [
                {**s, "status": "completed", "completed_at": now}
                for s in sub.get("submitters", [])
            ],
            "completed_at": now,
        },
    }


# ---------------------------------------------------------------------------
# Webhook signature verification.
# ---------------------------------------------------------------------------
def verify_webhook_signature(body: bytes, header_signature: str | None) -> bool:
    """Verify the `X-DocuSeal-Signature` header.

    DocuSeal signs the request body with HMAC-SHA256 using the configured
    webhook secret. If no secret is set, signature verification is skipped
    (dev mode); production deployments must set DOCUSEAL_WEBHOOK_SECRET.
    """
    if not settings.docuseal_webhook_secret:
        logger.warning("DocuSeal webhook secret not set — skipping signature verification")
        return True
    if not header_signature:
        return False
    digest = hmac.new(
        settings.docuseal_webhook_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, header_signature)
