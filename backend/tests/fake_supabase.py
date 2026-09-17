"""In-memory stand-in for ``app.db.supabase_client``.

Handlers talk to the adapter in Airtable-shaped records; this keeps those in
dicts and reuses the adapter's own mapping (``_schema``, ``_split_fields``,
``_row_to_record``), so a handler that writes a field the registry does not
know fails here exactly as it would against Postgres. Links are stored per
junction, which makes them symmetric the way the real junction tables are:
creating a Submission with ``Property=[pid]`` makes the property's
``Submissions`` read back with that id.

Not modelled: computed lookups (``Stage_Order`` - read the ``Stage`` link
instead), agency scope (everything is one agency), the read cache.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from app.db import supabase_client as at
from app.db.supabase_client import (
    And,
    Cond,
    Eq,
    IsBefore,
    Or,
    _row_to_record,
    _schema,
    _split_fields,
)


class FakeSupabase:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, dict[str, Any]]] = {}
        self._created: dict[str, datetime] = {}
        # junction name -> rows of {near_col: id, far_col: id, "position": n}
        self._junctions: dict[str, list[dict[str, Any]]] = {}
        # Test hook: return True for a (table, fields) to make that create
        # raise, for exercising rollback paths.
        self.fail_create: Callable[[str, dict], bool] | None = None

    # -- wiring ---------------------------------------------------------------
    def install(self, monkeypatch) -> None:
        for name in ("create", "get", "update", "delete", "search", "find_first", "all_records"):
            monkeypatch.setattr(at, name, getattr(self, name))

    def seed_stages(self, count: int = 9) -> None:
        for n in range(1, count + 1):
            self.create(at.TableNames.STAGES, {"Stage Name": f"Stage {n}", "Order": n})

    # -- test helpers -----------------------------------------------------------
    def rows(self, table: str) -> list[dict]:
        return [self._record(table, rid) for rid in self._rows.get(table, {})]

    def stage_id(self, order: int) -> str:
        rec = self.find_first(at.TableNames.STAGES, at.eq("Order", order))
        assert rec, f"stage {order} not seeded"
        return rec["id"]

    def link_count(self) -> int:
        return sum(len(v) for v in self._junctions.values())

    # -- adapter surface ----------------------------------------------------------
    def create(self, name: str, fields: dict) -> dict:
        if self.fail_create and self.fail_create(name, fields):
            raise RuntimeError(f"injected failure creating {name}")
        schema = _schema(name)
        scalars, links = _split_fields(schema, name, fields)
        rid = str(uuid.uuid4())
        self._rows.setdefault(name, {})[rid] = self._store(schema, scalars)
        self._created[rid] = datetime.now(timezone.utc)
        self._write_links(schema, rid, links)
        return self._record(name, rid)

    def get(self, name: str, record_id: str, *, fresh: bool = False) -> dict:
        if record_id not in self._rows.get(name, {}):
            raise KeyError(f"NOT_FOUND: no {name} record with id {record_id!r}")
        return self._record(name, record_id)

    def update(self, name: str, record_id: str, fields: dict) -> dict:
        schema = _schema(name)
        row = self._rows.get(name, {}).get(record_id)
        if row is None:
            raise KeyError(f"NOT_FOUND: no {name} record with id {record_id!r}")
        scalars, links = _split_fields(schema, name, fields)
        row.update(self._store(schema, scalars))
        self._write_links(schema, record_id, links)
        return self._record(name, record_id)

    def delete(self, name: str, record_id: str) -> dict:
        if self._rows.get(name, {}).pop(record_id, None) is None:
            raise KeyError(f"NOT_FOUND: no {name} record with id {record_id!r}")
        # Junction rows go with the row, as the FK cascade does.
        for junction, jrows in self._junctions.items():
            self._junctions[junction] = [r for r in jrows if record_id not in r.values()]
        return {"id": record_id, "deleted": True}

    def search(
        self, name: str, formula: Cond, max_records: int | None = None, *, fresh: bool = False,
    ) -> list[dict]:
        out = [r for r in self.rows(name) if self._matches(r["fields"], formula)]
        return out[:max_records] if max_records else out

    def find_first(self, name: str, formula: Cond, *, fresh: bool = False) -> dict | None:
        rows = self.search(name, formula, max_records=1)
        return rows[0] if rows else None

    def all_records(self, name: str, formula: Cond | None = None, *, fresh: bool = False) -> list[dict]:
        return self.search(name, formula) if formula is not None else self.rows(name)

    # -- internals ----------------------------------------------------------------
    @staticmethod
    def _store(schema, scalars: dict) -> dict:
        # Postgres hands numerics back as Decimal (which _convert_read then
        # normalises to int when whole); mirror that so 24000 reads as 24000,
        # not 24000.0. Json parameters are unwrapped to the value they carry.
        types = {c.name: c.type for c in schema.columns.values()}
        out: dict[str, Any] = {}
        for col, v in scalars.items():
            if v is not None and types.get(col) == "number":
                v = Decimal(str(v))
            out[col] = getattr(v, "obj", v)
        return out

    def _write_links(self, schema, rid: str, links: dict[str, list[str]]) -> None:
        # Replace-set per link field, as the adapter does.
        for at_name, ids in links.items():
            link = schema.links[at_name]
            jrows = [r for r in self._junctions.get(link.junction, []) if r.get(link.near) != rid]
            for pos, far_id in enumerate(ids):
                jrows.append({link.near: rid, link.far: far_id, "position": pos})
            self._junctions[link.junction] = jrows

    def _record(self, name: str, rid: str) -> dict:
        schema = _schema(name)
        row = dict(self._rows[name][rid])
        for i, at_name in enumerate(schema.links):
            link = schema.links[at_name]
            hits = sorted(
                (r for r in self._junctions.get(link.junction, []) if r.get(link.near) == rid),
                key=lambda r: r["position"],
            )
            row[f"_l{i}"] = [r[link.far] for r in hits]
        row["_id"] = rid
        row["_created"] = self._created[rid]
        return _row_to_record(schema, row)

    @classmethod
    def _matches(cls, fields: dict, cond: Cond | None) -> bool:
        if cond is None:
            return True
        if isinstance(cond, And):
            return all(cls._matches(fields, p) for p in cond.parts)
        if isinstance(cond, Or):
            return any(cls._matches(fields, p) for p in cond.parts)
        if isinstance(cond, Eq):
            v = fields.get(cond.field)
            if isinstance(v, list):  # link field: membership
                return cond.value in v
            if cond.value is False:  # Airtable checkbox: false matches unset too
                return not v
            return v == cond.value
        if isinstance(cond, IsBefore):
            v = fields.get(cond.field)
            return bool(v) and str(v) < str(cond.value)
        raise TypeError(f"unsupported condition {cond!r}")
