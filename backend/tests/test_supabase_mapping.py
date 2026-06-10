"""Pure-function tests for the Supabase adapter's field mapping.

No database needed: these exercise the Airtable-name <-> column translation,
record shaping and write coercion that every handler depends on.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.db.schema import SCHEMAS
from app.db.supabase_client import (
    TableNames,
    _coerce_write,
    _row_to_record,
    _select_sql,
    _split_fields,
)


# ---------------------------------------------------------------------------
# Registry consistency
# ---------------------------------------------------------------------------
def test_every_tablename_has_a_schema():
    for attr in dir(TableNames):
        if attr.startswith("_"):
            continue
        name = getattr(TableNames, attr)
        assert name in SCHEMAS, f"TableNames.{attr} = {name!r} missing from SCHEMAS"


def test_link_far_tables_exist():
    for name, schema in SCHEMAS.items():
        for fname, link in schema.links.items():
            assert link.far_table in SCHEMAS, f"{name}.{fname} -> {link.far_table!r} unknown"


def test_select_builds_for_every_table():
    for name, schema in SCHEMAS.items():
        sql = _select_sql(schema)
        assert sql.startswith("select ")
        assert f"from {schema.sql_table} t" in sql


# ---------------------------------------------------------------------------
# Read shaping — _row_to_record
# ---------------------------------------------------------------------------
def test_row_to_record_emits_airtable_names_and_omits_nulls():
    schema = SCHEMAS["properties"]
    link_names = list(schema.links.keys())
    row = {c.name: None for c in schema.columns.values()}
    row.update({
        "_id": "0b6f1a52-0000-4000-8000-000000000001",
        "_created": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        "address": "1 Test Street",
        "annual_rent": Decimal("24000.00"),
        "tc_signed": True,
        "stage_changed_at": date(2026, 6, 1),
    })
    for i in range(len(link_names)):
        row[f"_l{i}"] = []
    row[f"_l{link_names.index('Landlords')}"] = ["11111111-0000-4000-8000-000000000002"]
    row["_c0"] = 2  # Stage_Order lookup

    rec = _row_to_record(schema, row)
    f = rec["fields"]
    assert rec["id"] == "0b6f1a52-0000-4000-8000-000000000001"
    assert rec["createdTime"].startswith("2026-06-01T12:00:00")
    assert f["Address"] == "1 Test Street"
    assert f["Annual Rent "] == 24000          # trailing-space name preserved, Decimal -> int
    assert f["TC_Signed"] is True
    assert f["Stage changed at"] == "2026-06-01"
    assert f["Landlords"] == ["11111111-0000-4000-8000-000000000002"]
    assert f["Stage_Order"] == 2
    assert "Tenant" not in f                   # empty link omitted (Airtable behaviour)
    assert "Gate Block Reason" not in f        # nulls omitted


# ---------------------------------------------------------------------------
# Write splitting — _split_fields
# ---------------------------------------------------------------------------
def test_split_fields_routes_scalars_and_links():
    schema = SCHEMAS["properties"]
    scalars, links = _split_fields(schema, "properties", {
        "Address": "2 Example Road",
        "TC_Signed": True,
        "Landlords": ["11111111-0000-4000-8000-000000000002"],
        "Stage": ["22222222-0000-4000-8000-000000000003"],
    })
    assert scalars == {"address": "2 Example Road", "tc_signed": True}
    assert links == {
        "Landlords": ["11111111-0000-4000-8000-000000000002"],
        "Stage": ["22222222-0000-4000-8000-000000000003"],
    }


def test_split_fields_unknown_field_raises_unknown_field_name():
    # referencing.py matches on "UNKNOWN_FIELD_NAME" in the error text — keep it.
    with pytest.raises(KeyError, match="UNKNOWN_FIELD_NAME"):
        _split_fields(SCHEMAS["tenants"], "tenants", {"Nope": 1})


def test_split_fields_computed_is_read_only():
    with pytest.raises(KeyError, match="read-only"):
        _split_fields(SCHEMAS["properties"], "properties", {"Stage_Order": 4})


def test_split_fields_none_link_clears():
    _, links = _split_fields(SCHEMAS["properties"], "properties", {"Tenant": None})
    assert links == {"Tenant": []}


# ---------------------------------------------------------------------------
# Write coercion — _coerce_write
# ---------------------------------------------------------------------------
def test_coerce_empty_string_clears_field():
    # Airtable convention: writing "" blanks a field -> NULL relationally.
    assert _coerce_write("", "text") is None
    assert _coerce_write("", "date") is None


def test_coerce_types():
    assert _coerce_write("2026-06-10", "date") == "2026-06-10"
    assert _coerce_write(date(2026, 6, 10), "date") == date(2026, 6, 10)
    assert _coerce_write(1, "bool") is True
    assert _coerce_write("12", "int") == 12
    assert _coerce_write("12.5", "number") == 12.5
    assert _coerce_write(None, "text") is None
