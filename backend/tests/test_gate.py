"""Smoke tests for gate condition functions (spec §11.1)."""
from datetime import date, timedelta

from app.handlers.pg00_gate import TRANSITIONS


def _eval(target: int, fields: dict) -> list[str]:
    failures = []
    for label, fn in TRANSITIONS[target]:
        reason = fn(fields)
        if reason:
            failures.append(f"{label}: {reason}")
    return failures


def test_gate_1_to_2_pass():
    assert _eval(2, {"Landlords": ["rec1"]}) == []


def test_gate_1_to_2_fail():
    assert _eval(2, {"Landlords": []}) != []


def test_gate_2_to_3_all_pass():
    fields = {
        "Gas_Cert_Status": "On File",
        "EPC_Status": "On File",
        "EICR_Status": "On File",
        "EPC Rating": "C",
        "Gas Certificates Expiry": (date.today() + timedelta(days=120)).isoformat(),
        "EICR Expiry": (date.today() + timedelta(days=400)).isoformat(),
        "TC_Signed": True,
    }
    assert _eval(3, fields) == []


def test_gate_2_to_3_blocks_on_fg():
    fields = {
        "Gas_Cert_Status": "On File",
        "EPC_Status": "On File",
        "EICR_Status": "On File",
        "EPC Rating": "F",
        "Gas Certificates Expiry": (date.today() + timedelta(days=120)).isoformat(),
        "EICR Expiry": (date.today() + timedelta(days=400)).isoformat(),
        "TC_Signed": True,
    }
    failures = _eval(3, fields)
    assert any("EPC rating" in f for f in failures)


def test_gate_2_to_3_blocks_on_not_provided_epc():
    fields = {
        "Gas_Cert_Status": "On File",
        "EPC_Status": "Not Provided",
        "EICR_Status": "On File",
        "EPC Rating": "C",
        "Gas Certificates Expiry": (date.today() + timedelta(days=120)).isoformat(),
        "EICR Expiry": (date.today() + timedelta(days=400)).isoformat(),
        "TC_Signed": True,
    }
    assert any("EPC_Status" in f for f in _eval(3, fields))


def test_gate_6_to_7_requires_all_four():
    fields = {"TA_LL_Signed": True, "TA_TT_Signed": False, "TDS Cert On File": True, "Deposit Registered": True}
    failures = _eval(7, fields)
    assert any("TA_TT" in f for f in failures)


def test_gate_7_to_8_requires_apt_rra():
    fields = {
        "funds_cleared": True,
        "How_To_Rent_Served": True,
        "Gas_Cert_Served": True,
        "EPC_Served": True,
        "EICR_Served": True,
        "TDS_Info_Served": True,
        "RRA_Sheet_Served": False,
        "Works_Signed_Off": True,
        "Tenancy Type": "APT",
    }
    assert any("RRA" in f for f in _eval(8, fields))
