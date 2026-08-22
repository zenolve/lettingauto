"""Renewed certificates must reset the tenant's 'served' record.

A gas safety record / EICR renewed mid-tenancy has to be given to the EXISTING
tenant within 28 days of the inspection. The *_Served flags are set once by the
tenant pack, so without this the record would keep reading "served" against a
superseded copy and no prompt would ever fire.
"""
from app.routers.uploads import _apply_cert_expiry
from app.services.cert_renewal import BUCKET_EXPIRY_FIELD, detect_renewals as _detect_cert_renewals

SERVED_BEFORE = {
    "Address": "12 Example Street",
    "Gas Certificates Expiry": "2026-09-01",
    "Gas_Cert_Served": True,
    "EICR Expiry": "2028-01-01",
    "EICR_Served": True,
}


def _names(result):
    return sorted(doc for _flag, doc, _dtype in result)


def test_new_gas_expiry_clears_served():
    got = _detect_cert_renewals({"Gas Certificates Expiry": "2027-09-01"}, SERVED_BEFORE)
    assert _names(got) == ["Gas Safety Certificate"]
    assert got[0][0] == "Gas_Cert_Served"


def test_both_certs_renewed_together():
    got = _detect_cert_renewals(
        {"Gas Certificates Expiry": "2027-09-01", "EICR Expiry": "2033-01-01"},
        SERVED_BEFORE,
    )
    assert _names(got) == ["EICR", "Gas Safety Certificate"]


def test_unchanged_date_is_not_a_renewal():
    # Re-saving the same value (or an unrelated edit in the same PATCH) must not
    # invalidate a perfectly good served record.
    assert _detect_cert_renewals({"Gas Certificates Expiry": "2026-09-01"}, SERVED_BEFORE) == []


def test_cleared_date_is_not_a_renewal():
    assert _detect_cert_renewals({"Gas Certificates Expiry": None}, SERVED_BEFORE) == []


def test_never_served_property_is_untouched():
    # Pre-let: the tenant pack hasn't run, so there is no superseded copy and
    # nothing to re-serve. This is what scopes the behaviour to live tenancies.
    before = {"Gas Certificates Expiry": "2026-09-01", "Gas_Cert_Served": False}
    assert _detect_cert_renewals({"Gas Certificates Expiry": "2027-09-01"}, before) == []


def test_unrelated_field_ignored():
    assert _detect_cert_renewals({"funds_cleared": True}, SERVED_BEFORE) == []


# --- upload path: the certificate file and its expiry travel together -------

def test_upload_of_non_cert_bucket_needs_no_expiry():
    assert _apply_cert_expiry("prop-1", "photos", None) == {}


def test_cert_upload_without_expiry_asks_for_it():
    out = _apply_cert_expiry("prop-1", "gas_cert", None)
    assert out["expiry_required"] is True
    assert out["expiry_field"] == "Gas Certificates Expiry"


def test_cert_upload_with_bad_date_asks_again():
    out = _apply_cert_expiry("prop-1", "eicr", "not-a-date")
    assert out["expiry_required"] is True
    assert "YYYY-MM-DD" in out["expiry_error"]


def test_bucket_map_covers_gas_and_eicr_only():
    # EPC is excluded on purpose: 10-year validity, no expiry field.
    assert set(BUCKET_EXPIRY_FIELD) == {"gas_cert", "eicr"}
