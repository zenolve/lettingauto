"""Per-stage sent-document records (``Sent_Documents`` table).

One structured row per document sent for a property — library letters,
prescribed-pack docs, offer / contract sends. Replaces the old habit of
overloading ``Submissions`` with "Library:" JSON-text rows.

All writers go through ``record_sent`` (best-effort — never raises into the
send path). The signing webhook calls ``update_status_by_envelope`` to flip a
row's status to Signed / Declined when the envelope completes, closing the
loop that used to be invisible.

Versioning (migration 004): a send can name the earlier send it revises. The
new row becomes the next version, the earlier one is marked superseded, and
the exact HTML that went out is kept in ``Sent_Document_Bodies`` so a later
revision can start from what the recipient actually received.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from app.core.logger import get_logger
from app.db import supabase_client as at

logger = get_logger(__name__)

# Library send "mode" <-> Channel single-select option.
_MODE_TO_CHANNEL = {"sign": "Sign", "email_pdf": "Email PDF", "email_html": "Email HTML"}
_CHANNEL_TO_MODE = {"Sign": "sign", "Email PDF": "email_pdf", "Email HTML": "email_html", "Attachment": "attachment"}

# Statuses after which an envelope can no longer be signed.
_ENVELOPE_CLOSED = {"Signed", "Declined", "Voided"}


def channel_for_mode(mode: str) -> str:
    return _MODE_TO_CHANNEL.get(mode, "Email HTML")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_sent(
    *,
    property_id: str,
    doc_id: str,
    doc_name: str,
    stage: Optional[int],
    channel: str,
    recipients: Optional[list[str]] = None,
    pdf_url: Optional[str] = None,
    envelope_id: Optional[str] = None,
    sent_by: str = "system",
    status: str = "Sent",
    revises_id: Optional[str] = None,
    body_html: Optional[str] = None,
) -> Optional[str]:
    """Create a ``Sent_Documents`` row. Best-effort: logs and returns None on
    failure rather than breaking the document send.

    ``revises_id`` names the earlier send this one replaces: the new row is
    its next version and the earlier row is marked superseded. ``body_html``
    is stored as the copy of what went out.
    """
    try:
        version = 1
        if revises_id:
            prev = at.get(at.TableNames.SENT_DOCUMENTS, revises_id).get("fields", {})
            version = int(prev.get("Version") or 1) + 1
        fields: dict[str, Any] = {
            "Name": f"{doc_name} · {date.today().isoformat()}",
            "Property": [property_id],
            "Doc ID": doc_id,
            "Doc Name": doc_name,
            "Stage": stage,
            "Channel": channel,
            "Recipients": ", ".join(recipients) if recipients else None,
            "Sent Date": date.today().isoformat(),
            "Sent By": sent_by,
            "PDF URL": pdf_url,
            "Envelope ID": envelope_id,
            "Status": status,
            "Version": version,
            "Revises ID": revises_id,
        }
        fields = {k: v for k, v in fields.items() if v is not None}
        rec = at.create(at.TableNames.SENT_DOCUMENTS, fields)
    except Exception as e:  # noqa: BLE001
        logger.warning("sent_documents.record_failed doc=%s err=%s", doc_id, e)
        return None

    # The send is on record from here; what follows must not undo that.
    if revises_id:
        try:
            at.update(at.TableNames.SENT_DOCUMENTS, revises_id, {"Superseded At": _now()})
        except Exception as e:  # noqa: BLE001
            logger.warning("sent_documents.supersede_failed prev=%s err=%s", revises_id, e)
    if body_html:
        try:
            at.create(at.TableNames.SENT_DOCUMENT_BODIES, {
                "Sent Document ID": rec["id"],
                "Body HTML": body_html,
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("sent_documents.body_store_failed id=%s err=%s", rec["id"], e)
    return rec["id"]


def update_status_by_envelope(envelope_id: Optional[str], status: str, *, completed: bool = False) -> bool:
    """Flip a sent doc's Status by its envelope id (signing webhook). No-op if
    no row matches (e.g. an envelope created before this table existed)."""
    if not envelope_id:
        return False
    try:
        row = at.find_first(at.TableNames.SENT_DOCUMENTS, at.eq("Envelope ID", envelope_id))
        if not row:
            return False
        if row["fields"].get("Superseded At"):
            # The agent sent a revision without voiding this envelope, and the
            # older version has now been signed. Recorded as-is; the property
            # page shows it against the superseded version so it is not missed.
            logger.warning("sent_documents.superseded_version_updated status=%s id=%s env=%s",
                           status, row["id"], envelope_id)
        upd: dict[str, Any] = {"Status": status}
        if completed:
            upd["Completed Date"] = date.today().isoformat()
        at.update(at.TableNames.SENT_DOCUMENTS, row["id"], upd)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("sent_documents.status_update_failed env=%s err=%s", envelope_id, e)
        return False


def mark_voided(sent_id: str) -> None:
    at.update(at.TableNames.SENT_DOCUMENTS, sent_id, {
        "Status": "Voided",
        "Completed Date": date.today().isoformat(),
    })


def get_sent(sent_id: str) -> dict:
    """One sent row. Raises KeyError when it does not exist for this agency."""
    return at.get(at.TableNames.SENT_DOCUMENTS, sent_id)


def get_body(sent_id: str) -> Optional[str]:
    """The stored copy of what a send delivered, or None when it predates
    versioning or was sent by a path that keeps only a PDF."""
    try:
        row = at.find_first(at.TableNames.SENT_DOCUMENT_BODIES, at.eq("Sent Document ID", sent_id))
    except Exception as e:  # noqa: BLE001
        logger.warning("sent_documents.body_read_failed id=%s err=%s", sent_id, e)
        return None
    return (row or {}).get("fields", {}).get("Body HTML") or None


def summarise(rec: dict) -> dict:
    """A sent row in the shape the property page and the editor consume.

    Keeps the original keys (``submission_id``, ``submitted_date``) the
    DocumentsSentOnStage widget already reads, plus the versioning fields.
    """
    f = rec.get("fields", {})
    recips = f.get("Recipients") or ""
    status = f.get("Status")
    return {
        "submission_id": rec["id"],
        "doc_id": f.get("Doc ID"),
        "doc_name": f.get("Doc Name"),
        "stage": f.get("Stage"),
        "mode": _CHANNEL_TO_MODE.get(f.get("Channel")),
        "recipients": [r.strip() for r in recips.split(",") if r.strip()],
        "pdf_url": f.get("PDF URL"),
        "submitted_date": f.get("Sent Date"),
        "sent_at": rec.get("createdTime"),
        "status": status,
        "completed_date": f.get("Completed Date"),
        "version": int(f.get("Version") or 1),
        "revises_id": f.get("Revises ID"),
        "superseded_at": f.get("Superseded At"),
        # An envelope that can still be signed - what "void previous" acts on.
        "envelope_open": bool(f.get("Envelope ID")) and status not in _ENVELOPE_CLOSED,
    }


def _rows_for_property(property_id: str) -> tuple[list[dict], Any]:
    """The property's sent rows, and when its current tenancy cycle began."""
    from app.services.tenancies import cycle_started_at  # noqa: PLC0415 — avoid load cycle
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        return [], None
    f = prop.get("fields", {})
    rows: list[dict] = []
    for rid in f.get("Sent_Documents") or []:
        try:
            rows.append(at.get(at.TableNames.SENT_DOCUMENTS, rid))
        except Exception:
            continue
    return rows, cycle_started_at(f)


def _previous_tenancy(summary: dict, cycle_start: Any) -> bool:
    """Sent during a tenancy a re-let has since archived. Take-on, compliance
    and marketing documents (the landlord's terms of business, say) belong to
    the property and stay current across a re-let."""
    from app.services.tenancies import FIRST_TENANCY_STAGE, belongs_to_previous_tenancy  # noqa: PLC0415
    return ((summary.get("stage") or 0) >= FIRST_TENANCY_STAGE
            and belongs_to_previous_tenancy(summary.get("sent_at"), cycle_start))


def list_for_property(property_id: str) -> list[dict]:
    """Return a property's sent-doc rows newest-first, in the shape the
    DocumentsSentOnStage widget expects. ``revisable`` marks library documents
    the agent can open again as a revision (system sends such as the
    prescribed pack are not editable documents)."""
    from app.services.document_library import get_document  # noqa: PLC0415 — avoid load cycle

    raw, cycle = _rows_for_property(property_id)
    rows = [summarise(r) for r in raw]
    for r in rows:
        r["revisable"] = get_document(r["doc_id"] or "") is not None
        # Shown under "Previous tenancies" rather than on the stage it was sent at.
        r["previous_tenancy"] = _previous_tenancy(r, cycle)
    # Version breaks ties: two sends inside one clock tick still list newest first.
    rows.sort(key=lambda r: (r.get("sent_at") or r.get("submitted_date") or "", r["version"]), reverse=True)
    return rows


def current_version(property_id: str, doc_id: str) -> Optional[dict]:
    """The latest send of ``doc_id`` on this property that nothing has
    replaced yet - what a new send of the same document would revise. A send
    from an archived tenancy is never offered: the next tenant's agreement is a
    new document, not a revision of the last one."""
    raw, cycle = _rows_for_property(property_id)
    heads = [
        s for s in (summarise(r) for r in raw)
        if s["doc_id"] == doc_id and not s["superseded_at"] and not _previous_tenancy(s, cycle)
    ]
    if not heads:
        return None
    return max(heads, key=lambda r: (r.get("sent_at") or "", r["version"]))
