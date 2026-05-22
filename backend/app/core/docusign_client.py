"""DocuSign eSignature client — JWT bearer auth + envelope creation.

Used when ``settings.app_env`` is ``dev`` or ``production`` (see ``signing.py``).
The mock auto-approve path used in ``test`` env stays in ``docuseal_client``.

Auth model: DocuSign JWT bearer grant
- Build a JWT signed RS256 with the integration's private key
- Exchange at ``https://{auth_server}/oauth/token`` for an access token
- Cache the access token in-process until ``expires_in`` is close (60s buffer)

First-time-only setup gotcha (call this out in any README):
    Before the first JWT exchange succeeds, the user being impersonated must
    grant the integration key consent. Visit
        https://{auth_server}/oauth/auth?
            response_type=code
            &scope=signature%20impersonation
            &client_id={integration_key}
            &redirect_uri={any_url}
    in a browser, sign in as the impersonation user, and click "Allow".
    Subsequent JWT exchanges work without further interaction.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import jwt

from app.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Access token cache — module-level so all callers in a single worker share
# one token. DocuSign access tokens last an hour; we refresh ~5 min early.
# ---------------------------------------------------------------------------
@dataclass
class _CachedToken:
    access_token: str
    expires_at: float   # epoch seconds


_token_cache: _CachedToken | None = None
_TOKEN_REFRESH_BUFFER_S = 300  # refresh 5 min before expiry


def _load_private_key() -> bytes:
    path = (settings.docusign_private_key_path or "").strip()
    if not path:
        raise RuntimeError(
            "DOCUSIGN_PRIVATE_KEY_PATH is not configured. Point it at the RSA "
            "private key file paired with the public key in DocuSign Admin → "
            "Apps and Keys → <integration key> → RSA Keypairs."
        )
    p = Path(path)
    if not p.is_file():
        raise RuntimeError(f"DocuSign private key file not found: {path}")
    return p.read_bytes()


def _ensure_creds() -> None:
    missing = [
        name for name, val in [
            ("DOCUSIGN_INTEGRATION_KEY", settings.docusign_integration_key),
            ("DOCUSIGN_USER_ID",         settings.docusign_user_id),
            ("DOCUSIGN_ACCOUNT_ID",      settings.docusign_account_id),
        ] if not (val or "").strip()
    ]
    if missing:
        raise RuntimeError(
            "DocuSign credentials missing: " + ", ".join(missing) +
            ". Set them in .env or switch APP_ENV to 'test' for the mock signer."
        )


def _normalise_base_path(base: str) -> str:
    """DocuSign's `baseUri` (returned by /oauth/userinfo) is the host root,
    but REST calls need ``/restapi/v2.1/...``. Accept either form in .env."""
    b = (base or "").rstrip("/")
    if not b:
        return ""
    if b.endswith("/restapi"):
        return b
    return f"{b}/restapi"


async def _fetch_access_token() -> str:
    _ensure_creds()
    private_key = _load_private_key()
    now = int(time.time())
    claims = {
        "iss":   settings.docusign_integration_key,
        "sub":   settings.docusign_user_id,
        "aud":   settings.docusign_auth_server,
        "iat":   now,
        "exp":   now + 60 * 60,           # 1 hour — DocuSign caps this
        "scope": "signature impersonation",
    }
    assertion = jwt.encode(claims, private_key, algorithm="RS256")

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"https://{settings.docusign_auth_server}/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion":  assertion,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if r.status_code != 200:
        # `consent_required` is the most common first-run failure — surface
        # the consent URL so the dev knows exactly what to click.
        try:
            err = r.json()
        except Exception:
            err = {"raw": r.text}
        if err.get("error") == "consent_required":
            consent_url = (
                f"https://{settings.docusign_auth_server}/oauth/auth"
                f"?response_type=code"
                f"&scope=signature%20impersonation"
                f"&client_id={settings.docusign_integration_key}"
                f"&redirect_uri=https://www.docusign.com"
            )
            raise RuntimeError(
                "DocuSign returned consent_required. Visit this URL once "
                "while signed in as the impersonation user, click Allow, "
                f"then retry:\n  {consent_url}"
            )
        raise RuntimeError(f"DocuSign token exchange failed ({r.status_code}): {err}")

    body = r.json()
    return body["access_token"]


async def _get_access_token() -> str:
    global _token_cache
    if _token_cache and _token_cache.expires_at > time.time() + _TOKEN_REFRESH_BUFFER_S:
        return _token_cache.access_token
    token = await _fetch_access_token()
    # Don't bother re-parsing expires_in from the response — DocuSign always
    # issues 3600s. Allow buffer to trigger a refresh ahead of real expiry.
    _token_cache = _CachedToken(access_token=token, expires_at=time.time() + 3600)
    logger.info("docusign.token.refreshed expires_at=%s",
                datetime.fromtimestamp(_token_cache.expires_at, tz=timezone.utc).isoformat())
    return token


# ---------------------------------------------------------------------------
# Envelope creation.
# ---------------------------------------------------------------------------
@dataclass
class EnvelopeSigner:
    """A recipient who must sign — gets an anchor tab."""
    name: str
    email: str
    role: str = "Signer"


@dataclass
class EnvelopeCc:
    """A recipient who only receives a copy — no signature requested."""
    name: str
    email: str
    role: str = "Recipient"


async def create_envelope(
    *,
    name: str,
    pdf_bytes: bytes,
    signers: list[EnvelopeSigner],
    ccs: list[EnvelopeCc],
    metadata: dict[str, Any],
    anchor_strings: list[str],
    email_subject: str | None = None,
) -> dict[str, Any]:
    """Push a PDF to DocuSign, place anchor tabs, send to signers.

    Returns DocuSign's envelope response: `{envelopeId, status, statusDateTime,
    uri}` plus our own ``signing_urls`` list (recipient view URLs are computed
    lazily by the agent UI if needed).

    The ``metadata`` dict travels with the envelope as `customFields.textCustomFields`
    so the Connect webhook can bind the completion back to the right Property.

    Anchor tabs: the first signer gets ``anchor_strings[0]``, the second gets
    ``anchor_strings[1]``. If only one signer is provided, the second anchor
    string is left untabbed in the PDF (still printed as raw text, harmless).
    """
    if not signers:
        raise ValueError("DocuSign envelope needs at least one signer.")
    if not anchor_strings:
        anchor_strings = ["/sig1/", "/sig2/"]

    token = await _get_access_token()
    base_path = _normalise_base_path(settings.docusign_base_path)
    if not base_path:
        raise RuntimeError(
            "DOCUSIGN_BASE_PATH is not configured. Set it to your account's "
            "baseUri (e.g. https://demo.docusign.net) — /restapi is appended "
            "automatically."
        )

    document_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    api_signers: list[dict[str, Any]] = []
    for i, s in enumerate(signers):
        # Each signer gets one signHere tab anchored at the i-th marker. If
        # there are more signers than anchor strings (3+) we wrap — agents
        # would only configure this deliberately and the library spec lists
        # the anchor strings, so we never silently 500 on the agent.
        anchor = anchor_strings[i % len(anchor_strings)]
        api_signers.append({
            "email":         s.email,
            "name":          s.name,
            "recipientId":   str(i + 1),
            "routingOrder":  "1",          # all signers in parallel by default
            "roleName":      s.role,
            "tabs": {
                "signHereTabs": [{
                    "anchorString":  anchor,
                    "anchorXOffset": "0",
                    "anchorYOffset": "0",
                    "anchorUnits":   "pixels",
                    "anchorIgnoreIfNotPresent": "true",
                }],
            },
        })

    api_ccs: list[dict[str, Any]] = []
    for j, c in enumerate(ccs):
        api_ccs.append({
            "email":        c.email,
            "name":         c.name,
            "recipientId":  str(len(signers) + j + 1),
            "routingOrder": "1",
            "roleName":     c.role,
        })

    custom_fields_text = [
        {"name": k, "value": str(v), "show": "false", "required": "false"}
        for k, v in metadata.items()
        if v is not None
    ]

    envelope_body: dict[str, Any] = {
        "emailSubject": email_subject or name,
        "documents": [{
            "documentBase64": document_b64,
            "name":           name,
            "fileExtension":  "pdf",
            "documentId":     "1",
        }],
        "recipients": {
            "signers":       api_signers,
        },
        "status": "sent",   # "sent" = fire signer emails immediately
        "customFields": {
            "textCustomFields": custom_fields_text,
        },
    }
    if api_ccs:
        envelope_body["recipients"]["carbonCopies"] = api_ccs

    url = f"{base_path}/v2.1/accounts/{settings.docusign_account_id}/envelopes"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
                "Accept":        "application/json",
            },
            json=envelope_body,
        )

    if r.status_code >= 300:
        try:
            err = r.json()
        except Exception:
            err = {"raw": r.text}
        raise RuntimeError(f"DocuSign envelope create failed ({r.status_code}): {err}")

    out = r.json()
    logger.info(
        "docusign.envelope.created id=%s status=%s signers=%d ccs=%d anchor=%s",
        out.get("envelopeId"), out.get("status"), len(api_signers), len(api_ccs),
        anchor_strings[: len(api_signers)],
    )
    return out


async def get_envelope_status(envelope_id: str) -> dict[str, Any]:
    """Fetch the current envelope state — handy when the Connect webhook hasn't
    landed yet (e.g. ngrok not running) and the agent wants to manually pull."""
    token = await _get_access_token()
    base_path = _normalise_base_path(settings.docusign_base_path)
    url = f"{base_path}/v2.1/accounts/{settings.docusign_account_id}/envelopes/{envelope_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 300:
        raise RuntimeError(f"DocuSign envelope status failed ({r.status_code}): {r.text}")
    return r.json()


async def get_envelope_recipients(envelope_id: str) -> dict[str, Any]:
    """List the envelope's recipients with their current status — used by the
    Connect-fallback path that normalises a manual poll into a webhook-shaped
    event for the existing pg04 handler."""
    token = await _get_access_token()
    base_path = _normalise_base_path(settings.docusign_base_path)
    url = (f"{base_path}/v2.1/accounts/{settings.docusign_account_id}"
           f"/envelopes/{envelope_id}/recipients")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 300:
        raise RuntimeError(f"DocuSign recipients fetch failed ({r.status_code}): {r.text}")
    return r.json()


async def get_envelope_custom_fields(envelope_id: str) -> dict[str, Any]:
    """The custom fields carry our `property_id`/`library_doc`/`kind` so the
    completion event can be bound back to the right Property."""
    token = await _get_access_token()
    base_path = _normalise_base_path(settings.docusign_base_path)
    url = (f"{base_path}/v2.1/accounts/{settings.docusign_account_id}"
           f"/envelopes/{envelope_id}/custom_fields")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 300:
        raise RuntimeError(f"DocuSign custom_fields fetch failed ({r.status_code}): {r.text}")
    return r.json()
