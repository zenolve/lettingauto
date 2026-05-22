"""Thin wrapper around `pyairtable` with retry/backoff and a stable surface.

The rest of the codebase uses these helpers — never the underlying pyairtable
objects directly — so we have one place to add tracing, caching, or schema
validation later.
"""
from __future__ import annotations

import time
from typing import Any, Iterable

from pyairtable import Api
from pyairtable.api.table import Table

from app.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Table accessors
# ---------------------------------------------------------------------------
class TableNames:
    PROPERTIES = "properties"
    LANDLORDS = "landlords"
    TENANTS = "tenants"
    DIARY = "diary"
    FINANCIALS = "financials"
    CHECKLIST = "checklist"
    SUBMISSIONS = "submissions"
    STAGES = "stages"
    GATE_LOG = "gate_log"
    COMPLIANCE = "compliance"


_TABLE_IDS = {
    TableNames.PROPERTIES: settings.airtable_table_properties,
    TableNames.LANDLORDS: settings.airtable_table_landlords,
    TableNames.TENANTS: settings.airtable_table_tenants,
    TableNames.DIARY: settings.airtable_table_diary,
    TableNames.FINANCIALS: settings.airtable_table_financials,
    TableNames.CHECKLIST: settings.airtable_table_checklist,
    TableNames.SUBMISSIONS: settings.airtable_table_submissions,
    TableNames.STAGES: settings.airtable_table_stages,
    TableNames.GATE_LOG: settings.airtable_table_gate_log,
    TableNames.COMPLIANCE: settings.airtable_table_compliance,
}


def _api() -> Api:
    if not settings.airtable_token:
        raise RuntimeError("AIRTABLE_TOKEN is not configured")
    return Api(settings.airtable_token)


def table(name: str) -> Table:
    table_id = _TABLE_IDS[name]
    return _api().table(settings.airtable_base_id, table_id)


# ---------------------------------------------------------------------------
# Retry helper — Airtable's free tier rate limit is 5 req/sec per base; 429
# responses are retried up to 3 times with a 2s backoff (per spec §9.3).
# ---------------------------------------------------------------------------
def with_retry(fn, *args, max_tries: int = 3, delay: float = 2.0, **kwargs):
    last: Exception | None = None
    for attempt in range(max_tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            last = e
            text = str(e)
            if "429" in text or "RATE_LIMITED" in text.upper():
                logger.warning("Airtable rate limit; retry %s in %ss", attempt + 1, delay)
                time.sleep(delay)
                continue
            raise
    assert last is not None
    raise last


# ---------------------------------------------------------------------------
# Convenience CRUD wrappers
# ---------------------------------------------------------------------------
def search(name: str, formula: str, max_records: int | None = None) -> list[dict]:
    """Return matching records as a list of `{id, fields, ...}` dicts."""
    t = table(name)
    if max_records:
        return with_retry(t.all, formula=formula, max_records=max_records)
    return with_retry(t.all, formula=formula)


def find_first(name: str, formula: str) -> dict | None:
    rows = search(name, formula, max_records=1)
    return rows[0] if rows else None


def get(name: str, record_id: str) -> dict:
    return with_retry(table(name).get, record_id)


def create(name: str, fields: dict) -> dict:
    logger.info("airtable.create table=%s keys=%s", name, list(fields))
    return with_retry(table(name).create, fields)


def update(name: str, record_id: str, fields: dict) -> dict:
    logger.info("airtable.update table=%s id=%s keys=%s", name, record_id, list(fields))
    return with_retry(table(name).update, record_id, fields)


def all_records(name: str, formula: str | None = None) -> list[dict]:
    t = table(name)
    if formula:
        return with_retry(t.all, formula=formula)
    return with_retry(t.all)


# ---------------------------------------------------------------------------
# Formula builders — these dodge the f-string/curly-brace footgun (spec §8.3).
# ---------------------------------------------------------------------------
def eq(field: str, value: Any) -> str:
    """Build `{Field}=` formula safely."""
    if isinstance(value, bool):
        rhs = "TRUE()" if value else "FALSE()"
    elif isinstance(value, (int, float)):
        rhs = str(value)
    else:
        # escape any inner double-quotes
        rhs = '"{}"'.format(str(value).replace('"', '\\"'))
    return "{{{0}}}={1}".format(field, rhs)


def and_(*parts: str) -> str:
    return "AND({})".format(", ".join(parts))


def or_(*parts: str) -> str:
    return "OR({})".format(", ".join(parts))


def first_link(field_value: Iterable[str] | None) -> str | None:
    """Airtable linked record fields are lists of record IDs; return first or None."""
    if not field_value:
        return None
    items = list(field_value)
    return items[0] if items else None
