"""Provider-agnostic signing dispatch.

Single seam between the library /send route and whatever signing backend is
active for this deployment. Switches on ``settings.app_env``:

    dev / production →  DocuSign (real envelopes, real signer emails)
    test             →  Mock auto-approve (the docuseal_client mock + an
                        immediate local webhook fire — no network calls)

Anything else raises so misconfigs fail loud.

The dispatch returns a unified ``SignSubmission`` so callers don't branch on
provider — the only place this leaks is the webhook receiver, which has one
route per provider but normalises everything into the same downstream handler
(``app.handlers.pg04_docuseal.handle_docuseal_event``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.core.docusign_client import (
    EnvelopeCc,
    EnvelopeSigner,
    create_envelope,
)
from app.core.docuseal_client import (
    MOCK_DOCUSEAL_SUBMISSIONS,
    _mock_submission,
    mock_signed_event,
)
from app.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------
@dataclass
class SigningRecipient:
    """One person on a sign request. ``mandatory=True`` ⇒ signer (gets an
    anchor tab). ``mandatory=False`` ⇒ CC (envelope sent for visibility only).

    Note: a recipient marked mandatory=False is only added as CC when the
    payload also has at least one mandatory signer alongside them (this is
    the standard DocuSign envelope shape — a CC-only envelope has no signers
    and can't be sent). The /send route enforces that.
    """
    role: str
    name: str
    email: str
    mandatory: bool = True


@dataclass
class SignSubmission:
    """Unified envelope handle returned by every provider."""
    provider: str                  # "docusign" | "mock"
    id: str                        # envelope_id (DocuSign) / submission_id (mock)
    status: str                    # provider-native status string
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "id": self.id, "status": self.status, "raw": self.raw}


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------
def _provider_for_env() -> str:
    env = (settings.app_env or "").lower()
    if env == "test":
        return "mock"
    if env in ("dev", "development", "production", "prod"):
        return "docusign"
    raise RuntimeError(
        f"Unsupported APP_ENV={settings.app_env!r}. Set it to 'dev', 'production', or 'test'."
    )


async def send_for_signature(
    *,
    name: str,
    pdf_bytes: bytes,
    recipients: list[SigningRecipient],
    metadata: dict[str, Any],
    anchor_strings: list[str] | None = None,
    email_subject: str | None = None,
) -> SignSubmission:
    """Route a sign request to the active provider.

    Args:
        name:           Envelope / submission name. Also used as the email
                        subject if ``email_subject`` is None.
        pdf_bytes:      Rendered document bytes — sent to the provider as-is.
        recipients:     Ordered list. Mandatory recipients become signers
                        (anchored to the matching index in ``anchor_strings``);
                        non-mandatory ones become CCs.
        metadata:       Goes onto the envelope's custom fields. Must contain
                        ``property_id`` so the webhook can re-bind to the
                        right Property record on completion.
        anchor_strings: Per-position anchor markers. Defaults to ["/sig1/", "/sig2/"].
        email_subject:  Optional override; defaults to ``name``.
    """
    if not recipients:
        raise ValueError("At least one recipient required.")

    signers   = [r for r in recipients if r.mandatory]
    ccs       = [r for r in recipients if not r.mandatory]
    if not signers:
        raise ValueError(
            "At least one mandatory signer required. CC-only envelopes "
            "aren't supported by DocuSign."
        )

    provider = _provider_for_env()

    if provider == "docusign":
        ds_signers = [EnvelopeSigner(name=r.name, email=r.email, role=r.role) for r in signers]
        ds_ccs     = [EnvelopeCc(name=r.name, email=r.email, role=r.role)     for r in ccs]
        env = await create_envelope(
            name=name,
            pdf_bytes=pdf_bytes,
            signers=ds_signers,
            ccs=ds_ccs,
            metadata=metadata,
            anchor_strings=anchor_strings or ["/sig1/", "/sig2/"],
            email_subject=email_subject,
        )
        return SignSubmission(
            provider="docusign",
            id=str(env.get("envelopeId", "")),
            status=str(env.get("status", "sent")),
            raw=env,
        )

    if provider == "mock":
        # Bare-minimum submitter dicts in the shape docuseal_client.mock_signed_event
        # expects — preserves the existing pg04_docuseal regression path.
        submitters_payload = [
            {"role": r.role, "name": r.name, "email": r.email}
            for r in signers
        ]
        mock = _mock_submission(name=name, submitters=submitters_payload, metadata=metadata)
        return SignSubmission(
            provider="mock",
            id=mock["id"],
            status=mock["status"],
            raw=mock,
        )

    # Unreachable — _provider_for_env raises if env is wrong.
    raise RuntimeError(f"Unknown signing provider: {provider}")


async def replay_mock_completion(submission_id: str, doc_name: str) -> dict[str, Any]:
    """Fire a synthetic completion against the local DocuSeal webhook handler.

    Only used in ``test`` env, immediately after a successful ``send_for_signature``
    call returned a mock submission. Lets the test loop see the full
    PG_04 → gate-advance flow with no external HTTP.
    """
    from app.handlers.pg04_docuseal import handle_docuseal_event  # local — avoid load-time cycle

    if submission_id not in MOCK_DOCUSEAL_SUBMISSIONS:
        raise ValueError(f"Mock submission {submission_id} not found; can't replay.")
    fake = mock_signed_event(submission_id, doc_name)
    return await handle_docuseal_event(fake)


# ---------------------------------------------------------------------------
# DocuSign → existing handler normaliser
# ---------------------------------------------------------------------------
def normalise_docusign_event(connect_payload: dict[str, Any]) -> dict[str, Any]:
    """Convert a DocuSign Connect (JSON) event payload into the shape the
    existing PG_04 handler already understands.

    Connect payload shape (eventNotification → applicationDefined "Envelope Events"):
        {
          "event": "envelope-completed" | "envelope-declined" | ...,
          "apiVersion": "v2.1",
          "uri": "/...",
          "retryCount": 0,
          "generatedDateTime": "...",
          "data": {
            "accountId": "...",
            "envelopeId": "...",
            "envelopeSummary": {
              "status": "completed",
              "emailSubject": "Agency Terms & Conditions 2026",
              "customFields": { "textCustomFields": [{"name": "property_id", "value": "rec..."}, ...]},
              "recipients": { "signers": [...], "carbonCopies": [...] }
            }
          }
        }

    Handler expects:
        {
          "event": "submission.completed" | "submission.declined" | ...,
          "data": {
            "submission_id": <envelope id>,
            "template": {"name": <env subject / doc title>},
            "metadata": {... custom fields flattened ...},
            "submitters": [{"email":..., "name":..., "status":...}, ...],
          }
        }
    """
    event = (connect_payload.get("event") or "").lower()
    data = connect_payload.get("data") or {}
    envelope_id = data.get("envelopeId") or connect_payload.get("envelopeId") or ""
    summary = data.get("envelopeSummary") or {}
    if not summary:
        # Some Connect configurations put fields at the top of `data` instead
        # of under `envelopeSummary`.
        summary = data

    # ---- Map event name -----------------------------------------------------
    if "decline" in event:
        mapped_event = "submission.declined"
    elif "complete" in event or "sign" in event:
        mapped_event = "submission.completed"
    else:
        mapped_event = event or "submission.updated"

    # ---- Flatten custom fields → metadata ----------------------------------
    custom_fields = (summary.get("customFields") or {}).get("textCustomFields") or []
    metadata = {cf.get("name"): cf.get("value") for cf in custom_fields if cf.get("name")}

    # ---- Submitters: signers + carbon copies, with their status ------------
    recips = summary.get("recipients") or {}
    submitters: list[dict[str, Any]] = []
    for s in recips.get("signers") or []:
        submitters.append({
            "email":  s.get("email"),
            "name":   s.get("name"),
            "role":   s.get("roleName"),
            "status": (s.get("status") or "").lower(),  # "completed" / "declined" / "sent" / ...
            "completed_at": s.get("signedDateTime") or s.get("deliveredDateTime"),
        })
    for c in recips.get("carbonCopies") or []:
        submitters.append({
            "email":  c.get("email"),
            "name":   c.get("name"),
            "role":   c.get("roleName"),
            "status": (c.get("status") or "").lower(),
        })

    # Prefer the envelope's own emailSubject (set when we created it). If the
    # Connect config doesn't include envelope data in the payload, look the
    # library doc id up in the catalog so we still get a human-readable name
    # for the agent summary email and the kind-derivation regex.
    template_name = summary.get("emailSubject")
    if not template_name and metadata.get("library_doc"):
        try:
            from app.services.document_library import get_document  # noqa: PLC0415 — avoid load-time cycle
            doc = get_document(metadata["library_doc"])
            if doc:
                template_name = doc.name
        except Exception:
            pass
    template_name = template_name or metadata.get("library_doc") or "DocuSign envelope"

    return {
        "event": mapped_event,
        "data": {
            "submission_id": envelope_id,
            "template": {"name": template_name},
            "metadata": metadata,
            "submitters": submitters,
            "completed_at": summary.get("completedDateTime") or datetime.now(timezone.utc).isoformat(),
            "_provider": "docusign",
        },
    }
