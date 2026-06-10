"""Per-stage sent-document records (``Sent_Documents`` table).

One structured row per document sent for a property â€” library letters,
prescribed-pack docs, offer / contract sends. Replaces the old habit of
overloading ``Submissions`` with "Library:" JSON-text rows.

All writers go through ``record_sent`` (best-effort â€” never raises into the
send path). The signing webhook calls ``update_status_by_envelope`` to flip a
row's status to Signed / Declined when the envelope completes, closing the
loop that used to be invisible.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from app.core.logger import get_logger
from app.db import supabase_client as at

logger = get_logger(__name__)

# Library send "mode" <-> Channel single-select option.
_MODE_TO_CHANNEL = {"sign": "Sign", "email_pdf": "Email PDF", "email_html": "Email HTML"}
_CHANNEL_TO_MODE = {"Sign": "sign", "Email PDF": "email_pdf", "Email HTML": "email_html", "Attachment": "attachment"}


def channel_for_mode(mode: str) -> str:
    return _MODE_TO_CHANNEL.get(mode, "Email HTML")


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
) -> Optional[str]:
    """Create a ``Sent_Documents`` row. Best-effort: logs and returns None on
    failure rather than breaking the document send."""
    try:
        fields: dict[str, Any] = {
            "Name": f"{doc_name} Â· {date.today().isoformat()}",
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
        }
        fields = {k: v for k, v in fields.items() if v is not None}
        rec = at.create(at.TableNames.SENT_DOCUMENTS, fields)
        return rec["id"]
    except Exception as e:  # noqa: BLE001
        logger.warning("sent_documents.record_failed doc=%s err=%s", doc_id, e)
        return None


def update_status_by_envelope(envelope_id: Optional[str], status: str, *, completed: bool = False) -> bool:
    """Flip a sent doc's Status by its envelope id (signing webhook). No-op if
    no row matches (e.g. an envelope created before this table existed)."""
    if not envelope_id:
        return False
    try:
        row = at.find_first(at.TableNames.SENT_DOCUMENTS, at.eq("Envelope ID", envelope_id))
        if not row:
            return False
        upd: dict[str, Any] = {"Status": status}
        if completed:
            upd["Completed Date"] = date.today().isoformat()
        at.update(at.TableNames.SENT_DOCUMENTS, row["id"], upd)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("sent_documents.status_update_failed env=%s err=%s", envelope_id, e)
        return False


def list_for_property(property_id: str) -> list[dict]:
    """Return a property's sent-doc rows newest-first, in the shape the
    DocumentsSentOnStage widget expects (plus ``status`` / ``completed_date``)."""
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        return []
    ids = prop.get("fields", {}).get("Sent_Documents") or []
    rows: list[dict] = []
    for rid in ids:
        try:
            f = at.get(at.TableNames.SENT_DOCUMENTS, rid).get("fields", {})
        except Exception:
            continue
        recips = f.get("Recipients") or ""
        rows.append({
            "submission_id": rid,
            "doc_id": f.get("Doc ID"),
            "doc_name": f.get("Doc Name"),
            "stage": f.get("Stage"),
            "mode": _CHANNEL_TO_MODE.get(f.get("Channel")),
            "recipients": [r.strip() for r in recips.split(",") if r.strip()],
            "pdf_url": f.get("PDF URL"),
            "submitted_date": f.get("Sent Date"),
            "status": f.get("Status"),
            "completed_date": f.get("Completed Date"),
        })
    rows.sort(key=lambda r: r.get("submitted_date") or "", reverse=True)
    return rows
