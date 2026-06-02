"""One-time creator for the Airtable ``Offers`` table.

Builds the offer-lifecycle table approved on 2026-05-25 (keystone for Gap 4
offer lifecycle + Gap 5 multiple competing offers). Idempotent: if an
``Offers`` table already exists it prints its id and exits without changes.

Run from ``backend/``:

    python -m scripts.create_offers_table

Requires ``AIRTABLE_TOKEN`` (with schema-write / meta scope) and
``AIRTABLE_BASE_ID`` in the environment / .env — the same creds the app uses.

After creation, add the printed table id to ``.env`` as
``AIRTABLE_TABLE_OFFERS=<id>`` so the app can reference it when the Gap 5
handler rewrite lands.
"""
from __future__ import annotations

import sys

import httpx

from app.config import settings

META = "https://api.airtable.com/v0/meta/bases"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.airtable_token}",
        "Content-Type": "application/json",
    }


def _list_tables(base: str) -> list[dict]:
    r = httpx.get(f"{META}/{base}/tables", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json().get("tables", [])


def _table_id_by_name(tables: list[dict], name: str) -> str:
    for t in tables:
        if t["name"] == name:
            return t["id"]
    raise SystemExit(f"Could not find linked table {name!r} in base — aborting.")


def build_fields(properties_id: str, tenants_id: str) -> list[dict]:
    """The 18-field schema. First entry is the primary field."""
    iso_date = {"dateFormat": {"name": "iso"}}
    gbp = {"precision": 2, "symbol": "£"}  # £
    return [
        # 1 — primary
        {"name": "Name", "type": "singleLineText"},
        # 2,3 — links (auto-create reverse fields on Properties / Tenant)
        {"name": "Property", "type": "multipleRecordLinks",
         "options": {"linkedTableId": properties_id}},
        {"name": "Tenants", "type": "multipleRecordLinks",
         "options": {"linkedTableId": tenants_id}},
        # 4 — lifecycle
        {"name": "Status", "type": "singleSelect", "options": {"choices": [
            {"name": "Pending"},
            {"name": "Accepted"},
            {"name": "Rejected_By_Landlord"},
            {"name": "Withdrawn_By_Tenant"},
            {"name": "Expired"},
            {"name": "Failed_Referencing"},
            {"name": "Superseded"},
        ]}},
        # 5-11 — commercial snapshot
        {"name": "Offered Rent", "type": "currency", "options": gbp},
        {"name": "Rent Frequency", "type": "singleSelect", "options": {"choices": [
            {"name": "Monthly"}, {"name": "Weekly"},
        ]}},
        {"name": "Deposit", "type": "currency", "options": gbp},
        {"name": "Holding Deposit", "type": "currency", "options": gbp},
        {"name": "Start Date", "type": "date", "options": iso_date},
        {"name": "End Date", "type": "date", "options": iso_date},
        {"name": "Tenancy Term", "type": "singleLineText"},
        # 12-13 — operational
        {"name": "Holding Deposit Deadline", "type": "date", "options": iso_date},
        {"name": "DocuSign Envelope ID", "type": "singleLineText"},
        # 14-17 — audit
        {"name": "Created At", "type": "date", "options": iso_date},
        {"name": "Closed At", "type": "date", "options": iso_date},
        {"name": "Close Reason", "type": "singleLineText"},
        {"name": "Created By", "type": "singleLineText"},
        # 18
        {"name": "Notes", "type": "multilineText"},
    ]


def main() -> None:
    base = settings.airtable_base_id
    if not base or not settings.airtable_token:
        raise SystemExit("AIRTABLE_BASE_ID / AIRTABLE_TOKEN not configured.")

    tables = _list_tables(base)
    existing = next((t for t in tables if t["name"] == "Offers"), None)
    if existing:
        print(f"[skip] 'Offers' table already exists: id={existing['id']}")
        print(f"       Add to .env if missing:  AIRTABLE_TABLE_OFFERS={existing['id']}")
        return

    properties_id = _table_id_by_name(tables, "Properties")
    tenants_id = _table_id_by_name(tables, "Tenant")  # live base names it singular
    print(f"[info] linking Property -> {properties_id}, Tenants -> {tenants_id}")

    payload = {
        "name": "Offers",
        "description": "One row per tenant offer (joint applicants share a row). "
                       "Lifecycle wrapper around Properties.Tenant.",
        "fields": build_fields(properties_id, tenants_id),
    }
    r = httpx.post(f"{META}/{base}/tables", headers=_headers(), json=payload, timeout=60)
    if r.status_code >= 300:
        print(f"[error] create failed ({r.status_code}): {r.text}", file=sys.stderr)
        raise SystemExit(1)

    out = r.json()
    print(f"[ok]   created 'Offers' table: id={out['id']}")
    print(f"       fields: {len(out.get('fields', []))}")
    print(f"\n       Next: add to backend/.env  ->  AIRTABLE_TABLE_OFFERS={out['id']}")


if __name__ == "__main__":
    main()
