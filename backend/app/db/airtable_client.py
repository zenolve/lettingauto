"""Thin wrapper around `pyairtable` with retry/backoff and a stable surface.

The rest of the codebase uses these helpers — never the underlying pyairtable
objects directly — so we have one place to add tracing, caching, or schema
validation later.
"""
from __future__ import annotations

import threading
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
    OFFERS = "offers"
    SENT_DOCUMENTS = "sent_documents"


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
    TableNames.OFFERS: settings.airtable_table_offers,
    TableNames.SENT_DOCUMENTS: settings.airtable_table_sent_documents,
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
# In-memory read cache.
#
# Cuts Airtable API spend — we were re-reading whole tables on every dashboard
# load and reading the Stages table on every gate evaluation. Read-through
# with per-table TTLs; writes bust the whole table's entries.
#
# NOTE (multi-worker): this cache is PER-PROCESS. It's correct for the current
# single-process uvicorn. If you ever run multiple workers (--workers N /
# gunicorn / horizontal scaling) each worker keeps its own cache, so a write on
# one worker won't invalidate the others — they only self-heal within the TTL.
# At that point, move to a shared Redis cache behind this same surface.
#
# Cached reads are returned BY REFERENCE — callers must treat Airtable records
# as immutable (the codebase already builds new dicts for responses and never
# mutates the source records).
# ---------------------------------------------------------------------------
_MISS = object()
_TTL_REFERENCE = 600    # near-static tables (Stages, Tenancy Checklist)
_TTL_OPERATIONAL = 30   # everything else
_REFERENCE_TABLES = {TableNames.STAGES, TableNames.CHECKLIST}

# Disabled under the test env so unit tests stay deterministic.
CACHE_ENABLED = (settings.app_env or "").lower() != "test"


def _ttl_for(name: str) -> int:
    return _TTL_REFERENCE if name in _REFERENCE_TABLES else _TTL_OPERATIONAL


class _TTLCache:
    """Tiny thread-safe TTL cache. Keys are tuples whose element [1] is the
    table name, so a whole table can be invalidated in one pass."""

    def __init__(self) -> None:
        self._d: dict[tuple, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple) -> Any:
        with self._lock:
            item = self._d.get(key)
            if item is None:
                return _MISS
            expires_at, value = item
            if time.monotonic() >= expires_at:
                self._d.pop(key, None)
                return _MISS
            return value

    def set(self, key: tuple, value: Any, ttl: float) -> None:
        with self._lock:
            self._d[key] = (time.monotonic() + ttl, value)

    def invalidate_table(self, name: str) -> int:
        with self._lock:
            keys = [k for k in self._d if len(k) > 1 and k[1] == name]
            for k in keys:
                self._d.pop(k, None)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()


_cache = _TTLCache()


def invalidate(name: str) -> None:
    """Drop every cached read for a table. Called automatically by create /
    update. Call it directly before a read that must reflect out-of-band
    Airtable edits (e.g. the re-evaluate-gate flow)."""
    _cache.invalidate_table(name)


def clear_cache() -> None:
    """Drop the whole cache (used by tests / a manual flush)."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Convenience CRUD wrappers (read-through cached; writes invalidate)
# ---------------------------------------------------------------------------
def search(name: str, formula: str, max_records: int | None = None, *, fresh: bool = False) -> list[dict]:
    """Return matching records as a list of `{id, fields, ...}` dicts.

    ``fresh=True`` bypasses the cache for this read (and does not refresh it).
    """
    key = ("search", name, formula, max_records)
    if CACHE_ENABLED and not fresh:
        hit = _cache.get(key)
        if hit is not _MISS:
            return hit
    t = table(name)
    if max_records:
        rows = with_retry(t.all, formula=formula, max_records=max_records)
    else:
        rows = with_retry(t.all, formula=formula)
    if CACHE_ENABLED and not fresh:
        _cache.set(key, rows, _ttl_for(name))
    return rows


def find_first(name: str, formula: str, *, fresh: bool = False) -> dict | None:
    rows = search(name, formula, max_records=1, fresh=fresh)
    return rows[0] if rows else None


def get(name: str, record_id: str, *, fresh: bool = False) -> dict:
    key = ("get", name, record_id)
    if CACHE_ENABLED and not fresh:
        hit = _cache.get(key)
        if hit is not _MISS:
            return hit
    val = with_retry(table(name).get, record_id)
    if CACHE_ENABLED and not fresh:
        _cache.set(key, val, _ttl_for(name))
    return val


def create(name: str, fields: dict) -> dict:
    logger.info("airtable.create table=%s keys=%s", name, list(fields))
    res = with_retry(table(name).create, fields)
    invalidate(name)
    return res


def update(name: str, record_id: str, fields: dict) -> dict:
    logger.info("airtable.update table=%s id=%s keys=%s", name, record_id, list(fields))
    res = with_retry(table(name).update, record_id, fields)
    invalidate(name)
    return res


def all_records(name: str, formula: str | None = None, *, fresh: bool = False) -> list[dict]:
    key = ("all", name, formula)
    if CACHE_ENABLED and not fresh:
        hit = _cache.get(key)
        if hit is not _MISS:
            return hit
    t = table(name)
    if formula:
        rows = with_retry(t.all, formula=formula)
    else:
        rows = with_retry(t.all)
    if CACHE_ENABLED and not fresh:
        _cache.set(key, rows, _ttl_for(name))
    return rows


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
