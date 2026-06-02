"""Unit tests for the dashboard's pure aggregation helpers.

The aggregation endpoint itself hits Airtable, but the classification logic is
a pure function and is the part most likely to drift — so it's tested here.
"""
from datetime import date

from app.routers.dashboard import classify_compliance

TODAY = date(2026, 6, 1)


def test_epc_fg_is_bad():
    assert classify_compliance({"EPC Rating ": "F"}, TODAY) == "bad"
    assert classify_compliance({"EPC Rating ": "g"}, TODAY) == "bad"  # case-insensitive


def test_not_provided_is_bad():
    assert classify_compliance({"Gas_Cert_Status": "Not Provided"}, TODAY) == "bad"
    assert classify_compliance({"EICR_Status": "Not Provided"}, TODAY) == "bad"


def test_expired_on_file_cert_is_bad():
    assert classify_compliance(
        {"Gas_Cert_Status": "On File", "Gas Certificates Expiry": "2026-05-01"}, TODAY
    ) == "bad"


def test_expiring_within_30_days():
    out = classify_compliance(
        {
            "Gas_Cert_Status": "On File", "Gas Certificates Expiry": "2026-06-20",
            "EICR_Status": "On File", "EPC_Status": "On File",
        },
        TODAY,
    )
    assert out == "expiring"


def test_arranging_is_expiring():
    assert classify_compliance({"EPC_Status": "Palace Gate Arranging"}, TODAY) == "expiring"


def test_all_in_date_is_compliant():
    out = classify_compliance(
        {
            "Gas_Cert_Status": "On File", "Gas Certificates Expiry": "2030-01-01",
            "EICR_Status": "On File", "EICR Expiry": "2031-01-01",
            "EPC_Status": "On File", "EPC Rating ": "B",
        },
        TODAY,
    )
    assert out == "compliant"


def test_bad_takes_precedence_over_expiring():
    # EPC F/G (bad) wins even if a cert is also merely expiring.
    out = classify_compliance(
        {"EPC Rating ": "F", "Gas_Cert_Status": "On File", "Gas Certificates Expiry": "2026-06-10"},
        TODAY,
    )
    assert out == "bad"
