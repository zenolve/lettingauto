"""Verify the structured filter builders + their SQL compilation.

These replaced Airtable's filterByFormula strings: eq()/and_()/or_()/
is_before() build a condition tree which _cond_to_sql compiles to
parametrised SQL against the schema registry.
"""
import pytest

from app.db.schema import SCHEMAS
from app.db.supabase_client import _cond_to_sql, and_, eq, is_before, or_


def test_eq_text_compiles_to_param():
    sql, params = _cond_to_sql(SCHEMAS["landlords"], eq("Email Address", "a@b.com"))
    assert sql == "(t.email_address = %s)"
    assert params == ["a@b.com"]


def test_eq_bool_false_matches_unset_too():
    # Airtable's {Fired}=FALSE() matched both false and blank checkboxes;
    # the SQL equivalent is "is not true" (false OR null).
    sql, params = _cond_to_sql(SCHEMAS["diary"], eq("Fired", False))
    assert sql == "(t.fired is not true)"
    assert params == []


def test_eq_bool_true():
    sql, _ = _cond_to_sql(SCHEMAS["diary"], eq("Fired", True))
    assert sql == "(t.fired is true)"


def test_eq_number():
    sql, params = _cond_to_sql(SCHEMAS["stages"], eq("Order", 1))
    assert sql == "(t.stage_order = %s)"
    assert params == [1]


def test_and_join():
    f = and_(eq("Tenancy Type", "APT"), eq("RRA_Sheet_Served", False))
    sql, params = _cond_to_sql(SCHEMAS["properties"], f)
    assert sql == "((t.tenancy_type = %s) and (t.rra_sheet_served is not true))"
    assert params == ["APT"]


def test_or_join():
    f = or_(eq("Gate Status", "Blocked"), eq("Gate Status", "Clear"))
    sql, params = _cond_to_sql(SCHEMAS["properties"], f)
    assert sql == "((t.gate_status = %s) or (t.gate_status = %s))"
    assert params == ["Blocked", "Clear"]


def test_is_before_date():
    sql, params = _cond_to_sql(SCHEMAS["diary"], is_before("Alert_Date", "2026-06-10"))
    assert sql == "(t.alert_date < %s)"
    assert params == ["2026-06-10"]


def test_unknown_field_raises():
    with pytest.raises(KeyError, match="UNKNOWN_FIELD_NAME"):
        _cond_to_sql(SCHEMAS["properties"], eq("No Such Field", 1))


def test_raw_formula_string_rejected():
    # Old Airtable formula strings must fail loudly, not silently match nothing.
    with pytest.raises(TypeError):
        _cond_to_sql(SCHEMAS["properties"], "NOT({RRA_Sheet_Served})")
