"""Renewed certificates must reset the tenant's 'served' record.

A gas safety record / EICR renewed mid-tenancy has to be given to the EXISTING
tenant within 28 days of the inspection. The *_Served flags are set once by the
tenant pack, so without this the record would keep reading "served" against a
superseded copy and no prompt would ever fire.
"""
import io

import pytest
from fastapi import UploadFile

from app.core.auth import Agent
from app.routers import uploads
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


# ---------------------------------------------------------------------------
# The Uploads page route (/replace): new uploads and per-file Replace both go
# through it, so it must apply the expiry exactly as the plain upload routes do.
# ---------------------------------------------------------------------------

AGENT = Agent(email="agent@example.com")


@pytest.fixture
def let_property(fake_db, tmp_path, monkeypatch):
    """A live tenancy whose tenant was served the current gas cert and EICR."""
    monkeypatch.setattr(uploads, "UPLOADS_ROOT", tmp_path)
    return fake_db.create("properties", dict(SERVED_BEFORE))["id"]


def _pdf(name="new_cert.pdf"):
    return UploadFile(file=io.BytesIO(b"%PDF-1.4 certificate"), filename=name)


@pytest.mark.asyncio
async def test_replacing_a_served_gas_cert_records_expiry_and_prompts_reserve(let_property, fake_db, tmp_path):
    old = tmp_path / let_property / "gas_cert" / "20260101000000_abcd1234_old.pdf"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"%PDF old")

    out = await uploads.replace_uploaded_file(
        let_property, "gas_cert", file=_pdf(), delete_filename=old.name,
        expiry="2027-09-01", _=AGENT,
    )

    assert out["expiry_recorded"] == "2027-09-01"
    assert any("Gas Safety Certificate renewed" in n for n in out["notices"])
    pf = fake_db.get("properties", let_property)["fields"]
    assert pf["Gas Certificates Expiry"] == "2027-09-01"
    assert not pf.get("Gas_Cert_Served")             # the tenant holds a superseded copy
    assert pf.get("EICR_Served") is True             # untouched
    assert [d["fields"]["Diary_Type"] for d in fake_db.rows("diary")] == ["Gas Cert Re-serve"]
    stored = list((tmp_path / let_property / "gas_cert").iterdir())
    assert len(stored) == 1 and stored[0].name.endswith("_new_cert.pdf") and not old.exists()


@pytest.mark.asyncio
async def test_cert_replace_without_a_date_keeps_the_file_and_asks_for_it(let_property, fake_db, tmp_path):
    out = await uploads.replace_uploaded_file(
        let_property, "eicr", file=_pdf(), delete_filename=None, expiry=None, _=AGENT,
    )

    assert out["expiry_required"] is True and out["expiry_field"] == "EICR Expiry"
    pf = fake_db.get("properties", let_property)["fields"]
    assert pf["EICR Expiry"] == "2028-01-01" and pf["EICR_Served"] is True
    assert len(list((tmp_path / let_property / "eicr").iterdir())) == 1


@pytest.mark.asyncio
async def test_non_cert_upload_through_replace_ignores_expiry(let_property, fake_db):
    out = await uploads.replace_uploaded_file(
        let_property, "other", file=_pdf("letter.pdf"), delete_filename=None, expiry=None, _=AGENT,
    )

    assert not {"expiry_required", "expiry_recorded", "notices"} & set(out)
    assert fake_db.rows("diary") == []


def test_bucket_listing_names_the_expiry_field(let_property):
    meta = {b["name"]: b for b in uploads.list_known_buckets(let_property, _=AGENT)["buckets"]}
    assert meta["gas_cert"]["expiry_field"] == "Gas Certificates Expiry"
    assert meta["eicr"]["expiry_field"] == "EICR Expiry"
    assert meta["epc"]["expiry_field"] is None and meta["other"]["expiry_field"] is None
