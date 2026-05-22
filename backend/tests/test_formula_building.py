"""Verify the curly-brace-safe formula builders (spec §8.3)."""
from app.db.airtable_client import and_, eq


def test_eq_text_quotes_value():
    assert eq("Email Address", "a@b.com") == '{Email Address}="a@b.com"'


def test_eq_bool():
    assert eq("Fired", False) == "{Fired}=FALSE()"


def test_eq_number():
    assert eq("Order", 1) == "{Order}=1"


def test_and_join():
    f = and_(eq("Tenancy Type", "APT"), eq("RRA_Sheet_Served", False))
    assert f == 'AND({Tenancy Type}="APT", {RRA_Sheet_Served}=FALSE())'
