"""SMTP email client with agency-branded HTML templates.

Templates live in `app/templates/emails/*.html` and are Jinja2 rendered.
"""
from __future__ import annotations

import asyncio
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def render(template_name: str, **ctx: Any) -> str:
    # Emails are branded with the CURRENT AGENCY's identity (multi-tenant);
    # platform defaults apply when no agency scope is set.
    from app.core.branding import get_brand  # local import — avoid cycles
    b = get_brand()
    ctx.setdefault("brand_navy", b.navy)
    ctx.setdefault("brand_gold", b.gold)
    ctx.setdefault("brand_name", b.name)
    ctx.setdefault("agency_name", b.name)
    ctx.setdefault("agency_email", b.email)
    ctx.setdefault("agency_phone", b.phone)
    return _env.get_template(template_name).render(**ctx)


async def send_email(
    to: str | list[str],
    subject: str,
    html: str,
    *,
    cc: list[str] | None = None,
    reply_to: str | None = None,
    attachments: list[dict] | None = None,
    retries: int = 2,
    delay: float = 3.0,
) -> None:
    """Send an HTML email. Retries twice on failure (per spec §8.1).

    `attachments` is a list of dicts:
        {"filename": "GasCert.pdf", "content": <bytes>, "mime": "application/pdf"}
    """
    if not settings.smtp_host:
        att_info = f" attachments={len(attachments)}" if attachments else ""
        logger.warning("SMTP not configured — would send to=%s subject=%r%s", to, subject, att_info)
        return

    msg = EmailMessage()
    msg["From"] = settings.from_email
    msg["To"] = to if isinstance(to, str) else ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg.set_content("This message requires an HTML-capable email client.")
    msg.add_alternative(html, subtype="html")
    for att in attachments or []:
        mime = att.get("mime") or "application/octet-stream"
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(
            att["content"],
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=att["filename"],
        )

    # Port 465 wants implicit TLS (TLS from the first byte). Other ports with
    # smtp_use_tls=True upgrade an existing plaintext connection via STARTTLS.
    if settings.smtp_port == 465 and settings.smtp_use_tls:
        tls_kwargs = {"use_tls": True, "start_tls": False}
    else:
        tls_kwargs = {"start_tls": bool(settings.smtp_use_tls)}

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user or None,
                password=settings.smtp_pass or None,
                timeout=20,
                **tls_kwargs,
            )
            logger.info("email.sent to=%s subject=%r", msg["To"], subject)
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("email.send_failed attempt=%s err=%s", attempt + 1, e)
            if attempt < retries:
                await asyncio.sleep(delay)
    raise RuntimeError(f"SMTP send failed after {retries + 1} tries: {last_err}")


# ---------------------------------------------------------------------------
# High-level convenience wrappers — one per email ID in spec §8.2
# ---------------------------------------------------------------------------
async def send_admin_form_link(
    recipient_email: str, *, property_address: str, form_url: str, for_agent: bool = False,
) -> None:
    from app.core.branding import get_brand  # local import — avoid cycles
    html = render(
        "E01_admin_link.html",
        property_address=property_address,
        form_url=form_url,
        for_agent=for_agent,
    )
    subject = (
        f"Action needed — complete the landlord admin form for {property_address}"
        if for_agent
        else f"Welcome to {get_brand().name} — complete your property details"
    )
    await send_email(recipient_email, subject=subject, html=html)


async def send_verification_link(
    recipient_email: str, *, property_address: str, form_url: str, for_agent: bool = False,
) -> None:
    from app.core.branding import get_brand  # local import — avoid cycles
    html = render(
        "E03_verification_link.html",
        property_address=property_address,
        form_url=form_url,
        for_agent=for_agent,
    )
    subject = (
        f"Action needed — verification documents for {property_address}"
        if for_agent
        else f"{get_brand().name} — verify your identity"
    )
    await send_email(recipient_email, subject=subject, html=html)


async def send_agent_summary(
    agent_email: str,
    *,
    subject: str,
    template: str,
    context: dict[str, Any],
    cc: list[str] | None = None,
) -> None:
    html = render(template, **context)
    has_issues = bool(context.get("warnings") or context.get("actions"))
    prefix = "⚠️ Action Required: " if has_issues else "✅ All Clear: "
    await send_email(agent_email or settings.admin_email, subject=prefix + subject, html=html, cc=cc)
