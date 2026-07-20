"""Document library â€” browse, prepare, send.

Three endpoints surface the catalog defined in
``app/services/document_library.py``:

  GET  /api/library                              List entries (optionally filter by stage)
  GET  /api/library/{doc_id}/prepare/{property}  Body HTML + merge fields for the editor
  POST /api/library/{doc_id}/send/{property}     Action: "sign" | "email_pdf" | "email_html"

The send endpoint replaces the old per-template ``/api/contracts/.../submit``
single-action flow with three modes:

* ``sign``      â€” render the HTML to PDF, push to DocuSeal for e-signature.
                 (Mock DocuSeal kicks in automatically when no token is set.)
* ``email_pdf`` â€” render to PDF, attach to an email with the caller's custom
                 cover text and subject.
* ``email_html`` â€” send the edited HTML as the email body directly. No PDF.

All three persist a Submissions audit row so the flow board shows the action.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field

from app.core.auth import Agent, require_agent
from app.core.email_client import send_email
from app.core.logger import get_logger
from app.core.pdf_renderer import html_to_pdf, html_to_pdf_chromium, render_contract_html
from app.core.signing import SigningRecipient, replay_mock_completion, send_for_signature
from app.db import supabase_client as at
from app.routers.uploads import UPLOADS_ROOT, _public_url
from app.services.document_library import (
    DocMode,
    get_body,
    get_document,
    list_documents,
)
from app.services.merge_fields import MERGE_FIELD_CATALOGUE, build_merge_context

router = APIRouter(prefix="/api/library", tags=["library"])
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Browse
# ---------------------------------------------------------------------------
@router.get("")
def list_library(
    stage: Optional[int] = Query(None, ge=1, le=9, description="Filter to one stage (1-9)"),
    property_id: Optional[str] = Query(
        None,
        description="If given, hides docs that don't match the property's tenancy type "
                    "(e.g. APT TA on a Common Law property).",
    ),
    _: Agent = Depends(require_agent),
) -> dict:
    tenancy_type: Optional[str] = None
    if property_id:
        try:
            tenancy_type = at.get(at.TableNames.PROPERTIES, property_id) \
                .get("fields", {}).get("Tenancy Type")
        except Exception as e:  # noqa: BLE001
            logger.warning("library.tenancy_lookup_failed property=%s err=%s", property_id, e)

    docs = list_documents(stage, tenancy_type=tenancy_type)
    return {
        "tenancy_type": tenancy_type,
        "documents": [
            {
                "id": d.id,
                "name": d.name,
                "stage": d.stage,
                "default_mode": d.default_mode,
                "source": d.source,
                "signers": d.signers,
                "description": d.description,
                "has_real_content": d.source == "library_file",
                "tenancy_types": d.tenancy_types,
            }
            for d in docs
        ],
    }


# ---------------------------------------------------------------------------
# Base-template editor â€” agent updates the *underlying* HTML body of a
# library document. The change applies to every future property send. Files
# live at `app/templates/library/{doc_id}.html`. For TPLs that have never
# been edited (placeholder body), the first PUT promotes them from
# `master_doc` â†’ `library_file` on the next service restart.
# ---------------------------------------------------------------------------
@router.get("/{doc_id}/raw")
def get_raw_body(
    doc_id: str,
    _: Agent = Depends(require_agent),
) -> dict[str, Any]:
    """Return the raw, un-interpolated body of a library document.

    Used by the homepage library editor to edit the underlying template.
    """
    from app.services.document_library import _LIBRARY_DIR, get_body  # local import â€” avoid cycles
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(404, f"Unknown library document: {doc_id}")
    return {
        "doc_id": doc_id,
        "name": doc.name,
        "stage": doc.stage,
        "default_mode": doc.default_mode,
        "signers": doc.signers,
        "body_html": get_body(doc),
        "is_placeholder": doc.source == "master_doc",
    }


class TemplateUpdate(BaseModel):
    body_html: str


@router.put("/{doc_id}/raw")
def update_raw_body(
    doc_id: str,
    body: TemplateUpdate,
    _: Agent = Depends(require_agent),
) -> dict[str, Any]:
    """Persist a new base-template body for the given doc id.

    Writes to ``app/templates/library/{doc_id}.html``. The library catalog
    picks the file up automatically on next read via ``get_body()``. The
    in-memory catalog entry is also re-pointed to the file so the change is
    visible without a server restart.
    """
    from app.services.document_library import _LIBRARY_DIR, _BY_ID  # local import
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(404, f"Unknown library document: {doc_id}")
    target = _LIBRARY_DIR / f"{doc_id}.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.body_html, encoding="utf-8")
    # Hot-promote master_doc â†’ library_file so subsequent reads pick up the
    # new file in the same server process.
    if doc.source == "master_doc":
        import dataclasses
        _BY_ID[doc_id] = dataclasses.replace(doc, source="library_file", body_file=f"{doc_id}.html", placeholder_body=None)
    logger.info("library.template_updated doc=%s bytes=%d", doc_id, len(body.body_html))
    return {"doc_id": doc_id, "bytes": len(body.body_html)}


# ---------------------------------------------------------------------------
# Per-property / per-stage document queue.
#
# Workflow the user wanted: agent clicks "Browse document library" on a stage,
# hits [Add] on several documents. Added entries appear in a list under the
# browse button on that stage with [Open editor] / [Delete] per row. Persisted
# on disk so the queue survives a refresh.
#
# Storage: ``backend/uploads/_queues/<property_id>.json`` shaped like
# ``{"by_stage": {"2": ["pg_tcs_2026", "tpl_03"], "6": ["apt_pet_abnb"]}}``.
# Kept under the uploads root so it lives alongside the property's files
# rather than mixed in with application code.
# ---------------------------------------------------------------------------
_QUEUE_ROOT = UPLOADS_ROOT / "_queues"


def _queue_path(property_id: str) -> Path:
    _QUEUE_ROOT.mkdir(parents=True, exist_ok=True)
    return _QUEUE_ROOT / f"{property_id}.json"


def _read_queue(property_id: str) -> dict:
    p = _queue_path(property_id)
    if not p.exists():
        return {"by_stage": {}}
    try:
        import json
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"by_stage": {}}


def _write_queue(property_id: str, data: dict) -> None:
    import json
    _queue_path(property_id).write_text(json.dumps(data, indent=2), encoding="utf-8")


@router.get("/property/{property_id}/queue")
def get_queue(
    property_id: str,
    stage: Optional[int] = Query(None, ge=1, le=9),
    _: Agent = Depends(require_agent),
) -> dict:
    """Return queued (added but not yet sent) docs for a property.

    Optionally filtered to one stage. Each entry is enriched with the doc's
    name + default_mode + stage so the frontend can render the queue without
    a second fetch.
    """
    data = _read_queue(property_id)
    by_stage: dict[str, list[str]] = data.get("by_stage", {})
    queue: list[dict] = []
    for st, doc_ids in by_stage.items():
        if stage is not None and int(st) != stage:
            continue
        for doc_id in doc_ids:
            doc = get_document(doc_id)
            queue.append({
                "doc_id": doc_id,
                "stage": int(st),
                "name": doc.name if doc else doc_id,
                "default_mode": doc.default_mode if doc else None,
                "source": doc.source if doc else None,
                "has_real_content": (doc.source == "library_file") if doc else False,
            })
    return {"property_id": property_id, "queue": queue}


class QueueAdd(BaseModel):
    doc_id: str
    stage: int = Field(..., ge=1, le=9)


@router.post("/property/{property_id}/queue", status_code=status.HTTP_201_CREATED)
def add_to_queue(
    property_id: str,
    body: QueueAdd,
    _: Agent = Depends(require_agent),
) -> dict:
    if not get_document(body.doc_id):
        raise HTTPException(404, f"Unknown library document: {body.doc_id}")
    data = _read_queue(property_id)
    bucket = data.setdefault("by_stage", {})
    lst = bucket.setdefault(str(body.stage), [])
    if body.doc_id not in lst:
        lst.append(body.doc_id)
    _write_queue(property_id, data)
    logger.info("library.queue.add property=%s stage=%s doc=%s", property_id, body.stage, body.doc_id)
    return {"property_id": property_id, "queue": bucket.get(str(body.stage), [])}


@router.delete("/property/{property_id}/queue/{doc_id}")
def remove_from_queue(
    property_id: str,
    doc_id: str,
    stage: int = Query(..., ge=1, le=9),
    _: Agent = Depends(require_agent),
) -> dict:
    data = _read_queue(property_id)
    bucket = data.get("by_stage", {})
    lst = bucket.get(str(stage), [])
    if doc_id in lst:
        lst.remove(doc_id)
    _write_queue(property_id, data)
    logger.info("library.queue.delete property=%s stage=%s doc=%s", property_id, stage, doc_id)
    return {"property_id": property_id, "queue": lst}


@router.get("/property/{property_id}/sent")
def list_sent_for_property(
    property_id: str,
    _: Agent = Depends(require_agent),
) -> dict:
    """Return every document sent for a property, newest-first, from the
    structured ``Sent_Documents`` table. Drives the "Documents on this stage"
    widget â€” each row carries its stage, channel, status and (for sign /
    email_pdf) a link to the stored PDF."""
    from app.services import sent_documents as sd  # noqa: PLC0415
    return {"property_id": property_id, "sent": sd.list_for_property(property_id)}


# ---------------------------------------------------------------------------
# Prepare for editor
# ---------------------------------------------------------------------------
@router.get("/{doc_id}/prepare/{property_id}")
def prepare_library_doc(
    doc_id: str,
    property_id: str,
    _: Agent = Depends(require_agent),
) -> dict[str, Any]:
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(404, f"Unknown library document: {doc_id}")
    merge_ctx = build_merge_context(property_id)
    body_html = get_body(doc)
    return {
        "document": {
            "id": doc.id,
            "name": doc.name,
            "stage": doc.stage,
            "default_mode": doc.default_mode,
            "source": doc.source,
            "signers": doc.signers,
            "description": doc.description,
        },
        "body_html": body_html,
        "merge_fields": merge_ctx,
        "merge_field_catalogue": MERGE_FIELD_CATALOGUE,
    }


# ---------------------------------------------------------------------------
# Send â€” three modes
# ---------------------------------------------------------------------------
SendMode = Literal["sign", "email_pdf", "email_html"]


class Recipient(BaseModel):
    role: str = Field(default="Recipient", examples=["Landlord", "Tenant", "Agent"])
    name: str = ""
    email: EmailStr
    # True â†’ must sign (anchor tab placed); False â†’ CC (informational only,
    # envelope still routes to them). Defaults true so existing callers don't
    # need to change.
    mandatory: bool = True


class SendRequest(BaseModel):
    mode: SendMode
    title: str = Field(..., description="Subject / DocuSeal envelope title")
    body_html: str = Field(..., description="Edited document body (HTML)")
    recipients: list[Recipient] = Field(default_factory=list)
    # Used only when mode = email_pdf â€” wraps the attached PDF in a cover email
    email_cover_html: Optional[str] = None
    # Map of /pg_sigN/ anchor â†’ signature id, e.g. {"/pg_sig1/": "lesley_smith"}.
    # Unset slots fall back to the first available signature in the registry.
    signature_choices: dict[str, str] = Field(default_factory=dict)


_MERGE_TOKEN = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.IGNORECASE)


def _interpolate(html: str, ctx: dict[str, Any]) -> str:
    """Replace any remaining `{{key}}` tokens with values from `ctx`.

    Tokens whose key isn't in ctx are left untouched so the editor user can
    see what didn't get filled in (rather than silently empty).
    """
    def repl(m: re.Match) -> str:
        v = ctx.get(m.group(1))
        return str(v) if v is not None else m.group(0)
    return _MERGE_TOKEN.sub(repl, html)


_HTML_UNICODE_ASCII = {
    "\u2014": "--", "\u2013": "-", "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
    "\u2026": "...", "\u00a0": " ", "\u00a3": "GBP ", "\u20ac": "EUR ", "\u2022": "*", "\u2192": "->",
}


def _ascii_safe_html(s: str) -> str:
    """Normalise unicode â†’ ASCII-safe so fpdf2's core Helvetica can render it."""
    for k, v in _HTML_UNICODE_ASCII.items():
        s = s.replace(k, v)
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _render_pdf_with_fallback(
    final_body: str,
    title: str,
    *,
    signature_choices: dict[str, str] | None = None,
) -> bytes:
    """Render the document HTML to PDF.

    Primary: WeasyPrint (proper CSS rendering, branded shell).
    Fallback: fpdf2's ``write_html`` â€” keeps paragraphs, lists, headings,
    tables, line breaks. Used when WeasyPrint's native deps (GTK/Pango/Cairo)
    aren't available, typically on Windows dev machines.

    Production hosts should have WeasyPrint installed so the branded shell
    + page numbering work; the fallback is functional but plainer.
    """
    # Substitute any /pg_sigN/ anchors with the chosen agency signatory's
    # PNG BEFORE the contract shell wraps the body. The result is baked into
    # the PDF so DocuSign only sees the recipient-facing /sigN/ markers and
    # treats the agency's signature as static content.
    from app.services.pre_signatures import substitute as _pre_sig_substitute  # noqa: PLC0415
    body_with_sigs, _ = _pre_sig_substitute(final_body, choices=signature_choices)

    html = render_contract_html(body_with_sigs, title=title)

    # 1) Preferred: headless Chromium (Playwright). Pixel-identical to the
    #    editor preview because both use Chromium. Works on Windows.
    try:
        return html_to_pdf_chromium(html)
    except Exception as e:  # noqa: BLE001
        logger.warning("library.chromium_unavailable err=%s â€” trying WeasyPrint", e)

    # 2) Next: WeasyPrint (full CSS, needs GTK native libs â€” Linux prod).
    try:
        return html_to_pdf(html)
    except OSError as e:
        logger.warning("library.weasyprint_unavailable err=%s â€” using fpdf2 fallback", e)
    except Exception as e:  # noqa: BLE001
        logger.warning("library.weasyprint_failed err=%s â€” using fpdf2 fallback", e)

    # ---- fpdf2 fallback (last resort â€” plain layout) ---------------------
    # We feed the editor body HTML directly to fpdf2's HTML writer, which
    # honours <p> / <br> / <h1-6> / <b> / <i> / <ul>/<ol>/<li> / <table>.
    # That preserves paragraph breaks, bullets and headings â€” the earlier
    # `re.sub("<[^>]+>", " ", ...)` approach collapsed everything into one
    # wall of text (reported by the user in the screenshot dated 2026-05-16).
    from fpdf import FPDF  # local import â€” only required for the fallback path

    from app.core.branding import get_brand  # noqa: PLC0415 - agency-branded header
    _brand_name = get_brand().name

    class _PDF(FPDF):
        def header(self):
            # Navy title band on every page, mirroring the WeasyPrint shell.
            self.set_fill_color(0, 0x4A, 0xAD)
            self.rect(0, 0, 210, 14, "F")
            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", "B", 10)
            self.set_xy(15, 4.5)
            self.cell(0, 5, _ascii_safe_html(f"{_brand_name} â€” {title}"), ln=1)
            self.set_text_color(0, 0, 0)
            self.set_y(20)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(0x6B, 0x72, 0x80)
            self.cell(0, 5, f"Page {self.page_no()}", align="C")

    pdf = _PDF(format="A4")
    pdf.set_margins(18, 22, 18)
    pdf.set_auto_page_break(True, 18)
    pdf.add_page()
    pdf.set_font("Helvetica", "", 11)
    # `write_html` parses the body inline, emitting paragraphs / lists /
    # headings / tables. Use the signature-substituted body (NOT final_body)
    # so the baked-in /pg_sigN/ images appear in the fpdf2 output too.
    pdf.write_html(_ascii_safe_html(body_with_sigs)[:200_000])
    return bytes(pdf.output())


def _persist_doc_pdf(property_id: str, doc_id: str, pdf_bytes: bytes) -> str:
    """Save a generated PDF to disk under the property's uploads dir."""
    from datetime import datetime
    import secrets
    bucket = f"library_{doc_id}"
    target_dir = UPLOADS_ROOT / property_id / bucket
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    nonce = secrets.token_hex(4)
    filename = f"{stamp}_{nonce}_{doc_id}.pdf"
    (target_dir / filename).write_bytes(pdf_bytes)
    return _public_url(property_id, bucket, filename)


class PreviewRequest(BaseModel):
    body_html: str = Field(..., description="Current editor body â€” what the agent sees right now")
    # Optional /pg_sigN/ â†’ signature id map. Used by both preview and PDF
    # download so the agent sees the same baked-in signature they'd send.
    signature_choices: dict[str, str] = Field(default_factory=dict)


@router.post("/{doc_id}/pdf/{property_id}")
def download_library_pdf(
    doc_id: str,
    property_id: str,
    body: PreviewRequest,
    _: Agent = Depends(require_agent),
):
    """Render the document to PDF and stream the bytes back.

    Same rendering pipeline as ``/send`` (HTML â†’ WeasyPrint, fpdf2 fallback on
    Windows) â€” gives the agent the exact PDF that would be emailed/signed,
    but as a download so they can attach it from their own email client.
    """
    from fastapi.responses import Response  # local import â€” only this route needs it

    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(404, f"Unknown library document: {doc_id}")
    merge_ctx = build_merge_context(property_id)
    final_body = _interpolate(body.body_html, merge_ctx)
    pdf_bytes = _render_pdf_with_fallback(final_body, doc.name, signature_choices=body.signature_choices)

    # Filename: doc name + property address (slugged), keeps the agent's
    # download folder navigable.
    addr = (merge_ctx.get("property_address") or "").strip()
    parts = [doc.name]
    if addr:
        parts.append(addr)
    raw = " â€” ".join(parts)
    safe = "".join(c if c.isalnum() or c in " -_." else "_" for c in raw)[:120].strip() or "document"
    filename = f"{safe}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{doc_id}/preview/{property_id}")
def preview_library_doc(
    doc_id: str,
    property_id: str,
    body: PreviewRequest,
    _: Agent = Depends(require_agent),
) -> dict[str, Any]:
    """Render the final document â€” interpolated + wrapped in the brand shell.

    Returns the print-ready HTML the agent can drop into a preview iframe.
    Doesn't send anything or write to Airtable â€” pure projection.
    """
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(404, f"Unknown library document: {doc_id}")
    merge_ctx = build_merge_context(property_id)
    final_body = _interpolate(body.body_html, merge_ctx)
    # Bake the chosen pre-signatures in so the preview matches what the
    # recipient/DocuSign will actually see.
    from app.services.pre_signatures import substitute as _pre_sig_substitute  # noqa: PLC0415
    final_body, _ = _pre_sig_substitute(final_body, choices=body.signature_choices)
    rendered = render_contract_html(final_body, title=doc.name)
    return {
        "doc_id": doc_id,
        "title": doc.name,
        "html": rendered,
        # List of merge keys still unfilled so the editor can warn the user.
        "unresolved_tokens": _MERGE_TOKEN.findall(final_body),
    }


@router.post("/{doc_id}/send/{property_id}")
async def send_library_doc(
    doc_id: str,
    property_id: str,
    body: SendRequest,
    agent: Agent = Depends(require_agent),
) -> dict[str, Any]:
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(404, f"Unknown library document: {doc_id}")

    # Final interpolation against current Airtable values
    merge_ctx = build_merge_context(property_id)
    final_body = _interpolate(body.body_html, merge_ctx)

    # --- Mode dispatch --------------------------------------------------
    result: dict[str, Any] = {"doc_id": doc_id, "mode": body.mode, "title": body.title}

    if body.mode == "sign":
        if not body.recipients:
            raise HTTPException(400, "At least one recipient required for sign mode.")
        if not any(r.mandatory for r in body.recipients):
            raise HTTPException(
                400,
                "At least one recipient must be marked as a mandatory signer.",
            )
        pdf_bytes = _render_pdf_with_fallback(final_body, body.title, signature_choices=body.signature_choices)
        signing_recipients = [
            SigningRecipient(role=r.role, name=r.name, email=r.email, mandatory=r.mandatory)
            for r in body.recipients
        ]
        # Anchor strings: the LibraryDoc spec can override the defaults per-doc
        # (the T&C 2026 uses "/sig1/" and "/sig2/" baked into the source PDF).
        anchor_strings = getattr(doc, "anchor_strings", None) or ["/sig1/", "/sig2/"]

        submission = await send_for_signature(
            name=doc.name,   # used as the email subject + by _doc_kind() downstream
            pdf_bytes=pdf_bytes,
            recipients=signing_recipients,
            metadata={
                "property_id": property_id,
                "library_doc": doc_id,
                "kind":        "library_sign",
            },
            anchor_strings=anchor_strings,
            email_subject=body.title,
        )
        pdf_url = _persist_doc_pdf(property_id, doc_id, pdf_bytes)
        result.update({"submission": submission.to_dict(), "pdf_url": pdf_url})

        # In test env, fire the local mock-completion webhook against the same
        # PG_04 handler â€” keeps the existing fast-feedback loop intact. In dev /
        # production the real provider POSTs /webhook/docusign (or /docuseal-signed)
        # when a signer actually completes.
        if submission.provider == "mock":
            try:
                signed_result = await replay_mock_completion(submission.id, doc.name)
                result["mock_webhook"] = signed_result
                logger.info(
                    "library.mock_webhook_fired doc=%s submission=%s outcome=%s",
                    doc_id, submission.id, signed_result,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("library.mock_webhook_failed err=%s", e)
                result["mock_webhook_error"] = str(e)

    elif body.mode == "email_pdf":
        pdf_bytes = _render_pdf_with_fallback(final_body, body.title, signature_choices=body.signature_choices)
        if not body.recipients:
            raise HTTPException(400, "At least one recipient required for email_pdf mode.")
        cover = body.email_cover_html or f"<p>Please find <strong>{body.title}</strong> attached.</p>"
        pdf_url = _persist_doc_pdf(property_id, doc_id, pdf_bytes)
        sent: list[str] = []
        for r in body.recipients:
            try:
                await send_email(
                    r.email,
                    subject=body.title,
                    html=cover,
                    attachments=[{
                        "filename": f"{doc_id}.pdf",
                        "content": pdf_bytes,
                        "mime": "application/pdf",
                    }],
                )
                sent.append(r.email)
            except Exception as e:  # noqa: BLE001
                logger.warning("library.email_pdf.send_failed to=%s err=%s", r.email, e)
        result.update({"sent_to": sent, "pdf_url": pdf_url})

    elif body.mode == "email_html":
        if not body.recipients:
            raise HTTPException(400, "At least one recipient required for email_html mode.")
        sent: list[str] = []
        for r in body.recipients:
            try:
                await send_email(r.email, subject=body.title, html=final_body)
                sent.append(r.email)
            except Exception as e:  # noqa: BLE001
                logger.warning("library.email_html.send_failed to=%s err=%s", r.email, e)
        result.update({"sent_to": sent})

    # --- Record the send in Sent_Documents (per-stage audit) -----------
    # Structured row instead of the old Submissions "Library:" JSON-text hack.
    # The envelope id is stored so the signing webhook can flip Status to
    # Signed/Declined later (PG_04). Best-effort â€” never breaks the send.
    from app.services import sent_documents as sd  # noqa: PLC0415 â€” avoid load cycle
    submission_info = result.get("submission") or {}
    sd.record_sent(
        property_id=property_id,
        doc_id=doc_id,
        doc_name=doc.name,
        stage=doc.stage,
        channel=sd.channel_for_mode(body.mode),
        recipients=[r.email for r in body.recipients],
        pdf_url=result.get("pdf_url"),
        envelope_id=submission_info.get("id"),
        sent_by=getattr(agent, "email", None) or "agent",
        status="Sent",
    )
    return result
