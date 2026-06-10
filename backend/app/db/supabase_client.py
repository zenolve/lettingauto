"""Supabase (Postgres) data layer with the same surface the Airtable client had.

The rest of the codebase uses these helpers — never SQL directly — so the
swap from Airtable required changing only the import line at each call site.
Records keep the Airtable wire shape the app was built around:

    {"id": "<uuid>", "fields": {"<Airtable field name>": value, ...},
     "createdTime": "<iso datetime>"}

Field names (including the legacy trailing-space ones) are translated to real
columns via ``app/db/schema.py``; linked-record fields are junction tables and
behave symmetrically, exactly like Airtable links (writing
``Properties.Landlords`` is visible as ``Landlords.Properties`` and vice
versa). Airtable lookup fields (``Properties.Stage_Order``) are computed at
read time.

Filters are structured objects now — ``eq``/``and_``/``or_``/``is_before``
build a small condition tree that compiles to parametrised SQL (no string
formulas, no injection surface).

Connection: ``SUPABASE_DB_URL`` (the Postgres connection string from
Supabase → Settings → Database, or any local Postgres). A small connection
pool is created lazily on first use.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from app.config import settings
from app.core.logger import get_logger
from app.db.schema import SCHEMAS, TableSchema

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
    PAYMENTS = "payments"


def _schema(name: str) -> TableSchema:
    try:
        return SCHEMAS[name]
    except KeyError:
        raise KeyError(f"Unknown table {name!r} — not in app/db/schema.py") from None


# ---------------------------------------------------------------------------
# Connection pool (lazy — pure unit tests never open a connection)
# ---------------------------------------------------------------------------
_pool_lock = threading.Lock()
_pool: Any = None


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                if not settings.supabase_db_url:
                    raise RuntimeError(
                        "SUPABASE_DB_URL is not configured — set it to your Supabase "
                        "Postgres connection string (Settings → Database → Connection string)."
                    )
                from psycopg_pool import ConnectionPool  # local import — only needed at runtime

                _pool = ConnectionPool(
                    settings.supabase_db_url,
                    min_size=1,
                    max_size=settings.supabase_pool_max_size,
                    open=True,
                    kwargs={"autocommit": True},
                )
                logger.info("supabase.pool_opened max_size=%s", settings.supabase_pool_max_size)
    return _pool


def close_pool() -> None:
    """Close the pool (tests / graceful shutdown)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


# ---------------------------------------------------------------------------
# Retry helper — kept for surface parity; retries transient connection drops.
# ---------------------------------------------------------------------------
def with_retry(fn, *args, max_tries: int = 3, delay: float = 0.5, **kwargs):
    last: Exception | None = None
    for attempt in range(max_tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            last = e
            transient = e.__class__.__name__ in ("OperationalError", "PoolTimeout", "ConnectionTimeout")
            if transient and attempt < max_tries - 1:
                logger.warning("supabase.transient_error retry %s in %ss: %s", attempt + 1, delay, e)
                time.sleep(delay)
                continue
            raise
    assert last is not None
    raise last


# ---------------------------------------------------------------------------
# In-memory read cache (unchanged behaviour from the Airtable client).
#
# NOTE (multi-worker): PER-PROCESS — correct for single-process uvicorn. With
# multiple workers, move to Redis behind this same surface.
#
# Cached reads are returned BY REFERENCE — callers must treat records as
# immutable (the codebase already builds new dicts for responses).
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
    update / delete (for the written table AND every table reachable through
    its link fields — editing a link changes both sides' reads)."""
    _cache.invalidate_table(name)


def clear_cache() -> None:
    """Drop the whole cache (used by tests / a manual flush)."""
    _cache.clear()


def _invalidate_for_write(name: str) -> None:
    invalidate(name)
    for link in _schema(name).links.values():
        invalidate(link.far_table)


# ---------------------------------------------------------------------------
# Structured filters — replace Airtable's filterByFormula strings.
# ---------------------------------------------------------------------------
class Cond:
    """Base class for filter conditions."""


@dataclass(frozen=True)
class Eq(Cond):
    field: str
    value: Any


@dataclass(frozen=True)
class IsBefore(Cond):
    field: str
    value: Any  # ISO date string / date


@dataclass(frozen=True)
class And(Cond):
    parts: tuple


@dataclass(frozen=True)
class Or(Cond):
    parts: tuple


def eq(field: str, value: Any) -> Eq:
    """field == value. For checkbox/bool fields, ``eq(f, False)`` matches both
    false and unset — mirroring Airtable's ``{f}=FALSE()`` semantics."""
    return Eq(field, value)


def and_(*parts: Cond) -> And:
    return And(tuple(parts))


def or_(*parts: Cond) -> Or:
    return Or(tuple(parts))


def is_before(field: str, value: Any) -> IsBefore:
    """field < value (dates). Replaces Airtable ``IS_BEFORE({f}, ...)``."""
    return IsBefore(field, value)


def _cond_to_sql(schema: TableSchema, cond: Cond, alias: str = "t") -> tuple[str, list]:
    if isinstance(cond, Eq):
        col = schema.columns.get(cond.field)
        if col is None:
            raise KeyError(f"UNKNOWN_FIELD_NAME: {cond.field!r} is not filterable on {schema.sql_table!r}")
        if col.type == "bool":
            return (f"({alias}.{col.name} is true)" if cond.value
                    else f"({alias}.{col.name} is not true)"), []
        return f"({alias}.{col.name} = %s)", [_coerce_write(cond.value, col.type)]
    if isinstance(cond, IsBefore):
        col = schema.columns.get(cond.field)
        if col is None:
            raise KeyError(f"UNKNOWN_FIELD_NAME: {cond.field!r} is not filterable on {schema.sql_table!r}")
        return f"({alias}.{col.name} < %s)", [_coerce_write(cond.value, col.type)]
    if isinstance(cond, (And, Or)):
        if not cond.parts:
            return "(true)", []
        joiner = " and " if isinstance(cond, And) else " or "
        frags, params = [], []
        for p in cond.parts:
            f, ps = _cond_to_sql(schema, p, alias)
            frags.append(f)
            params.extend(ps)
        return "(" + joiner.join(frags) + ")", params
    raise TypeError(
        f"Unsupported filter {cond!r} — use the eq()/and_()/or_()/is_before() builders "
        "(raw Airtable formula strings are no longer supported)."
    )


# ---------------------------------------------------------------------------
# Value conversion
# ---------------------------------------------------------------------------
def _coerce_write(value: Any, typ: str) -> Any:
    """Python value → SQL parameter. Empty string clears a field (Airtable
    wrote '' to blank a column; NULL is the relational equivalent)."""
    if value is None or value == "":
        return None
    if typ == "bool":
        return bool(value)
    if typ == "int":
        return int(value)
    if typ == "number":
        return float(value)
    if typ == "json":
        from psycopg.types.json import Json  # local import — runtime only
        return Json(value)
    if typ in ("date", "timestamptz"):
        if isinstance(value, (date, datetime)):
            return value
        return str(value)  # ISO string; Postgres casts in assignment context
    return str(value) if not isinstance(value, str) else value


def _convert_read(value: Any) -> Any:
    """SQL value → JSON-friendly Python value in Airtable conventions."""
    if isinstance(value, Decimal):
        f = float(value)
        return int(f) if f.is_integer() else f
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


# ---------------------------------------------------------------------------
# SELECT machinery
# ---------------------------------------------------------------------------
def _select_sql(schema: TableSchema) -> str:
    parts = ["t.id as _id", "t.created_at as _created"]
    for at_name, col in schema.columns.items():
        parts.append(f"t.{col.name}")
    for i, (at_name, link) in enumerate(schema.links.items()):
        parts.append(
            f"(select coalesce(array_agg(j.{link.far}::text order by j.position, j.created_at), "
            f"'{{}}') from {link.junction} j where j.{link.near} = t.id) as _l{i}"
        )
    for i, (at_name, sub) in enumerate(schema.computed.items()):
        parts.append(f"{sub.format(alias='t')} as _c{i}")
    return f"select {', '.join(parts)} from {schema.sql_table} t"


def _row_to_record(schema: TableSchema, row: dict) -> dict:
    fields: dict[str, Any] = {}
    for at_name, col in schema.columns.items():
        v = row.get(col.name)
        if v is None:
            continue  # Airtable omits empty fields
        fields[at_name] = _convert_read(v)
    for i, at_name in enumerate(schema.links.keys()):
        ids = row.get(f"_l{i}") or []
        if ids:
            fields[at_name] = list(ids)
    for i, at_name in enumerate(schema.computed.keys()):
        v = row.get(f"_c{i}")
        if v is not None:
            fields[at_name] = _convert_read(v)
    created = row.get("_created")
    return {
        "id": str(row["_id"]),
        "fields": fields,
        "createdTime": created.isoformat() if isinstance(created, datetime) else created,
    }


def _query_records(
    name: str,
    cond: Cond | None,
    max_records: int | None = None,
    record_id: str | None = None,
) -> list[dict]:
    schema = _schema(name)
    sql = _select_sql(schema)
    params: list = []
    if record_id is not None:
        sql += " where t.id = %s"
        params.append(record_id)
    elif cond is not None:
        frag, ps = _cond_to_sql(schema, cond)
        sql += f" where {frag}"
        params.extend(ps)
    sql += " order by t.created_at, t.id"
    if max_records:
        sql += " limit %s"
        params.append(max_records)

    from psycopg.rows import dict_row  # local import — runtime only

    def _run():
        with _get_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    rows = with_retry(_run)
    return [_row_to_record(schema, r) for r in rows]


# ---------------------------------------------------------------------------
# Convenience CRUD wrappers (read-through cached; writes invalidate)
# ---------------------------------------------------------------------------
def search(name: str, formula: Cond, max_records: int | None = None, *, fresh: bool = False) -> list[dict]:
    """Return matching records as a list of `{id, fields, ...}` dicts.

    ``formula`` is a structured condition from eq()/and_()/or_()/is_before().
    ``fresh=True`` bypasses the cache for this read (and does not refresh it).
    """
    key = ("search", name, repr(formula), max_records)
    if CACHE_ENABLED and not fresh:
        hit = _cache.get(key)
        if hit is not _MISS:
            return hit
    rows = _query_records(name, formula, max_records)
    if CACHE_ENABLED and not fresh:
        _cache.set(key, rows, _ttl_for(name))
    return rows


def find_first(name: str, formula: Cond, *, fresh: bool = False) -> dict | None:
    rows = search(name, formula, max_records=1, fresh=fresh)
    return rows[0] if rows else None


def get(name: str, record_id: str, *, fresh: bool = False) -> dict:
    key = ("get", name, record_id)
    if CACHE_ENABLED and not fresh:
        hit = _cache.get(key)
        if hit is not _MISS:
            return hit
    rows = _query_records(name, None, record_id=record_id)
    if not rows:
        raise KeyError(f"NOT_FOUND: no {name} record with id {record_id!r}")
    val = rows[0]
    if CACHE_ENABLED and not fresh:
        _cache.set(key, val, _ttl_for(name))
    return val


def _split_fields(schema: TableSchema, name: str, fields: dict) -> tuple[dict, dict]:
    """Partition an Airtable-style fields dict into (scalar columns, links)."""
    scalars: dict[str, Any] = {}
    links: dict[str, list[str]] = {}
    for k, v in fields.items():
        col = schema.columns.get(k)
        if col is not None:
            scalars[col.name] = _coerce_write(v, col.type)
            continue
        link = schema.links.get(k)
        if link is not None:
            if v is None:
                links[k] = []
            elif isinstance(v, str):
                links[k] = [v]
            else:
                links[k] = [str(x) for x in v]
            continue
        if k in schema.computed:
            raise KeyError(f"UNKNOWN_FIELD_NAME: {k!r} on {name!r} is a computed lookup — read-only")
        raise KeyError(f"UNKNOWN_FIELD_NAME: {k!r} is not a field on table {name!r}")
    return scalars, links


def _write_links(cur, schema: TableSchema, row_id: str, links: dict[str, list[str]]) -> None:
    """Replace-set semantics per link field, preserving list order."""
    for at_name, ids in links.items():
        link = schema.links[at_name]
        cur.execute(f"delete from {link.junction} where {link.near} = %s", [row_id])
        for pos, far_id in enumerate(ids):
            cur.execute(
                f"insert into {link.junction} ({link.near}, {link.far}, position) "
                f"values (%s, %s, %s) on conflict do nothing",
                [row_id, far_id, pos],
            )


def create(name: str, fields: dict) -> dict:
    logger.info("supabase.create table=%s keys=%s", name, list(fields))
    schema = _schema(name)
    scalars, links = _split_fields(schema, name, fields)

    def _run() -> str:
        with _get_pool().connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    if scalars:
                        cols = ", ".join(scalars.keys())
                        ph = ", ".join(["%s"] * len(scalars))
                        cur.execute(
                            f"insert into {schema.sql_table} ({cols}) values ({ph}) returning id",
                            list(scalars.values()),
                        )
                    else:
                        cur.execute(f"insert into {schema.sql_table} default values returning id")
                    new_id = str(cur.fetchone()[0])
                    _write_links(cur, schema, new_id, links)
                    return new_id

    new_id = with_retry(_run)
    _invalidate_for_write(name)
    return get(name, new_id, fresh=True)


def update(name: str, record_id: str, fields: dict) -> dict:
    logger.info("supabase.update table=%s id=%s keys=%s", name, record_id, list(fields))
    schema = _schema(name)
    scalars, links = _split_fields(schema, name, fields)

    def _run() -> None:
        with _get_pool().connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    if scalars:
                        sets = ", ".join(f"{c} = %s" for c in scalars)
                        cur.execute(
                            f"update {schema.sql_table} set {sets} where id = %s returning id",
                            [*scalars.values(), record_id],
                        )
                    else:
                        cur.execute(
                            f"update {schema.sql_table} set updated_at = now() where id = %s returning id",
                            [record_id],
                        )
                    if cur.fetchone() is None:
                        raise KeyError(f"NOT_FOUND: no {name} record with id {record_id!r}")
                    _write_links(cur, schema, record_id, links)

    with_retry(_run)
    _invalidate_for_write(name)
    return get(name, record_id, fresh=True)


def delete(name: str, record_id: str) -> dict:
    logger.info("supabase.delete table=%s id=%s", name, record_id)
    schema = _schema(name)

    def _run() -> None:
        with _get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"delete from {schema.sql_table} where id = %s returning id", [record_id])
                if cur.fetchone() is None:
                    raise KeyError(f"NOT_FOUND: no {name} record with id {record_id!r}")

    with_retry(_run)
    _invalidate_for_write(name)
    return {"id": record_id, "deleted": True}


def all_records(name: str, formula: Cond | None = None, *, fresh: bool = False) -> list[dict]:
    key = ("all", name, repr(formula) if formula is not None else None)
    if CACHE_ENABLED and not fresh:
        hit = _cache.get(key)
        if hit is not _MISS:
            return hit
    rows = _query_records(name, formula)
    if CACHE_ENABLED and not fresh:
        _cache.set(key, rows, _ttl_for(name))
    return rows


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------
def first_link(field_value: Iterable[str] | None) -> str | None:
    """Linked-record fields are lists of record IDs; return first or None."""
    if not field_value:
        return None
    items = list(field_value)
    return items[0] if items else None
