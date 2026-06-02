"""One-time creator for the Airtable ``Sent_Documents`` table.

Records every document sent for a property (library letters, prescribed-pack
docs, offer/contract sends) as a structured row — replacing the old
``Submissions`` "Library:" JSON-text hack. Approved 2026-06-01.

Idempotent: prints the id and exits if the table already exists.

Run from ``backend/``:

    python -m scripts.create_sent_documents_table

After creation, add the printed id to ``.env`` as
``AIRTABLE_TABLE_SENT_DOCUMENTS=<id>``.
"""
from __future__ import annotations

import sys

import httpx

from app.config import settings

META = "https://api.airtable.com/v0/meta/bases"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.airtable_token}", "Content-Type": "application/json"}


def _tables(base: str) -> list[dict]:
    r = httpx.get(f"{META}/{base}/tables", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json().get("tables", [])


def build_fields(properties_id: str) -> list[dict]:
    iso = {"dateFormat": {"name": "iso"}}
    return [
        {"name": "Name", "type": "singleLineText"},  # primary
        {"name": "Property", "type": "multipleRecordLinks", "options": {"linkedTableId": properties_id}},
        {"name": "Doc ID", "type": "singleLineText"},
        {"name": "Doc Name", "type": "singleLineText"},
        {"name": "Stage", "type": "number", "options": {"precision": 0}},
        {"name": "Channel", "type": "singleSelect", "options": {"choices": [
            {"name": "Sign"}, {"name": "Email PDF"}, {"name": "Email HTML"}, {"name": "Attachment"},
        ]}},
        {"name": "Recipients", "type": "multilineText"},
        {"name": "Sent Date", "type": "date", "options": iso},
        {"name": "Sent By", "type": "singleLineText"},
        {"name": "PDF URL", "type": "singleLineText"},
        {"name": "Envelope ID", "type": "singleLineText"},
        {"name": "Status", "type": "singleSelect", "options": {"choices": [
            {"name": "Sent"}, {"name": "Delivered"}, {"name": "Viewed"},
            {"name": "Signed"}, {"name": "Declined"}, {"name": "Voided"},
        ]}},
        {"name": "Completed Date", "type": "date", "options": iso},
    ]


def main() -> None:
    base = settings.airtable_base_id
    if not base or not settings.airtable_token:
        raise SystemExit("AIRTABLE_BASE_ID / AIRTABLE_TOKEN not configured.")

    tables = _tables(base)
    existing = next((t for t in tables if t["name"] == "Sent_Documents"), None)
    if existing:
        print(f"[skip] 'Sent_Documents' already exists: id={existing['id']}")
        print(f"       Add to .env:  AIRTABLE_TABLE_SENT_DOCUMENTS={existing['id']}")
        return

    properties_id = next((t["id"] for t in tables if t["name"] == "Properties"), None)
    if not properties_id:
        raise SystemExit("Could not find the Properties table — aborting.")

    payload = {
        "name": "Sent_Documents",
        "description": "One row per document sent for a property (library letters, "
                       "prescribed-pack docs, contract/offer sends). Per-stage sent audit.",
        "fields": build_fields(properties_id),
    }
    r = httpx.post(f"{META}/{base}/tables", headers=_headers(), json=payload, timeout=60)
    if r.status_code >= 300:
        print(f"[error] create failed ({r.status_code}): {r.text}", file=sys.stderr)
        raise SystemExit(1)
    out = r.json()
    print(f"[ok]   created 'Sent_Documents': id={out['id']} ({len(out.get('fields', []))} fields)")
    print(f"\n       Next: add to backend/.env  ->  AIRTABLE_TABLE_SENT_DOCUMENTS={out['id']}")


if __name__ == "__main__":
    main()
