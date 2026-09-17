"""Importing an already-running tenancy.

The design rule under test: an import is not a special record type. It creates
the same rows and is then walked through the same gates, so a tenancy only
reaches Live if its declared evidence actually satisfies the pipeline.
"""
import pytest
from pydantic import ValidationError

from datetime import date, timedelta

from app.handlers import pg00_gate, pg_import
from app.handlers.pg_import import (
    IMPORT_DOCUMENT_CHECKLIST,
    IMPORT_FORM_NAME,
    TARGET_STAGE,
    _annual_rent,
    _tenancy_term,
    handle_import,
    was_imported,
)
from app.models.common import ImportTenancyInput
from app.routers.uploads import ALLOWED_BUCKETS

BASE = dict(
    address="99 Import Street", post_code="SW1A 9ZZ",
    landlord_full_name="Ivy Importer", landlord_email="ivy@example.com",
    tenants=[{"full_name": "Tom Tenant", "email": "tom@example.com", "is_lead": True}],
    rent_amount=1850, start_date="2025-09-01",
)


def test_document_checklist_buckets_are_uploadable():
    # A checklist entry naming a bucket the upload route rejects would give the
    # agent an uploader that 400s.
    for doc in IMPORT_DOCUMENT_CHECKLIST:
        assert doc["bucket"] in ALLOWED_BUCKETS, doc["bucket"]


def test_import_targets_live_not_end_of_tenancy():
    assert TARGET_STAGE == 8


def test_annual_rent_by_frequency():
    assert _annual_rent(1000, "Monthly") == 12000
    assert _annual_rent(1000, "Weekly") == 52000


def test_periodic_when_no_end_date():
    m = ImportTenancyInput(**BASE)
    assert _tenancy_term(m) == "Periodic"


def test_fixed_term_months_from_dates():
    m = ImportTenancyInput(**BASE, end_date="2026-08-31")
    assert _tenancy_term(m) == "12 months"


def test_tenancy_type_left_for_derivation():
    # Unset means "derive from the annualised rent" (Housing Act 1988 threshold),
    # exactly as take-on does - the importer shouldn't have to know the rule.
    assert ImportTenancyInput(**BASE).tenancy_type is None


def test_end_date_must_follow_start():
    with pytest.raises(ValidationError):
        ImportTenancyInput(**BASE, end_date="2025-08-01")


def test_at_least_one_tenant_required():
    payload = dict(BASE, tenants=[])
    with pytest.raises(ValidationError):
        ImportTenancyInput(**payload)


def test_running_tenancy_defaults_to_funds_cleared():
    # A tenancy that is already running has, by definition, had its money in.
    m = ImportTenancyInput(**BASE)
    assert m.funds_cleared is True
    assert m.works_signed_off is True


def test_signed_and_served_default_to_false():
    # Nothing is assumed about compliance: every assertion must be made
    # explicitly by the agent, so a lazy import cannot silently reach Live.
    m = ImportTenancyInput(**BASE)
    for field in ("tc_signed", "ta_landlord_signed", "ta_tenants_signed",
                  "how_to_rent_served", "gas_cert_served", "epc_served",
                  "eicr_served", "tds_info_served", "deposit_registered",
                  "tds_cert_on_file"):
        assert getattr(m, field) is False, field


# --- silent-failure guards -------------------------------------------------
# These fields exist because their ABSENCE fails quietly: wrong tax treatment,
# an unpayable landlord, or a safety check that never ran.

def test_overseas_landlord_without_approval_number_triggers_withholding():
    from app.services.derivations import nrl_withholding_active
    m = ImportTenancyInput(**BASE, residency="Non-resident (overseas)")
    assert nrl_withholding_active(m.residency, m.nrl_approval_number) is True


def test_overseas_landlord_with_approval_number_does_not_withhold():
    from app.services.derivations import nrl_withholding_active
    m = ImportTenancyInput(**BASE, residency="Non-resident (overseas)",
                           nrl_approval_number="NRL12345")
    assert nrl_withholding_active(m.residency, m.nrl_approval_number) is False


def test_residency_rejects_freetext():
    # Only the two values the derivation understands; "Overseas" or "France"
    # would silently read as UK-resident.
    with pytest.raises(ValidationError):
        ImportTenancyInput(**BASE, residency="France")


def test_safety_answers_are_tri_state():
    # Unset must stay None ("not asked"), never coerce to a compliant "Yes".
    m = ImportTenancyInput(**BASE)
    assert m.smoke_detectors_fitted is None
    assert m.furniture_fire_regs is None


def test_payout_and_correspondence_fields_accepted():
    m = ImportTenancyInput(
        **BASE, bank_name="Test Bank", sort_code="11-22-33",
        account_name="A Landlord", account_number="12345678",
        landlord_full_address="1 Example Road", landlord_post_code="SW1A 1AA",
        landlord_mobile="07700 900000",
    )
    assert m.sort_code == "11-22-33"
    assert m.landlord_full_address == "1 Example Road"


def test_compliance_report_passes_bank_details_through():
    # Regression: omitting these made every import report "bank details
    # missing" even when they were supplied.
    from app.handlers.pg_import import _compliance_report
    m = ImportTenancyInput(**BASE, bank_name="B", sort_code="11-22-33",
                           account_name="A", account_number="123")
    rep = _compliance_report(m, gas_status="On File", epc_status="On File", eicr_status="On File")
    assert not any("Bank details missing" in a for a in rep["actions"])


def test_compliance_report_flags_missing_bank_details():
    from app.handlers.pg_import import _compliance_report
    m = ImportTenancyInput(**BASE)
    rep = _compliance_report(m, gas_status="On File", epc_status="On File", eicr_status="On File")
    assert any("Bank details missing" in a for a in rep["actions"])


# ---------------------------------------------------------------------------
# End to end through the fake adapter: real rows, real links, real gate walk.
# ---------------------------------------------------------------------------

def _full_evidence() -> dict:
    """Everything the gates read, declared true, with certificates in date."""
    far = (date.today() + timedelta(days=200)).isoformat()
    return dict(
        BASE,
        tenants=[
            {"full_name": "Tom Tenant", "email": "tom@example.com", "is_lead": True},
            {"full_name": "Tina Tenant", "email": "tina@example.com"},
        ],
        landlord_full_address="1 Example Road, London", landlord_post_code="W8 5LS",
        residency="UK Resident",
        bank_name="Example Bank", sort_code="11-22-33",
        account_name="Ivy Importer", account_number="12345678",
        smoke_detectors_fitted="Yes", furniture_fire_regs="Yes",
        deposit_amount=2100, gas_cert_expiry=far, eicr_expiry=far, epc_rating="C",
        deposit_registered=True, deposit_registration_date="2025-09-10", tds_cert_on_file=True,
        tc_signed=True, ta_landlord_signed=True, ta_tenants_signed=True,
        how_to_rent_served=True, gas_cert_served=True, epc_served=True, eicr_served=True,
        tds_info_served=True, rra_sheet_served=True,
    )


@pytest.mark.asyncio
async def test_complete_evidence_reaches_live_silently(fake_db, monkeypatch):
    sent: list = []

    async def _record_email(*a, **k):
        sent.append((a, k))
    monkeypatch.setattr(pg00_gate, "send_agent_summary", _record_email)

    res = await handle_import(ImportTenancyInput(**_full_evidence()), agent_email="agent@example.com")

    assert res["is_live"] is True
    assert (res["stage_reached"], res["blocked_at"], res["blockers"]) == (8, None, [])
    assert sent == [], "importing history must not email anyone"

    pf = fake_db.get("properties", res["property_id"])["fields"]
    assert pf["Stage"] == [fake_db.stage_id(8)]
    assert pf["Gate Status"] == "Clear"
    assert pf["Tenancy Type"] == "APT"
    assert pf["Annual Rent "] == 1850 * 12
    assert pf["Landlords"] == [res["landlord_id"]]
    assert pf["Tenant"] == res["tenant_ids"]
    assert pf["Agent_Forms_Email"] == "agent@example.com"

    # Links are symmetric: the landlord and each tenant point back.
    ll = fake_db.get("landlords", res["landlord_id"])["fields"]
    assert ll["Properties"] == [res["property_id"]]
    assert ll["Verification Status"] == "Verified"
    assert not ll.get("NRL_Withholding_Active")
    tenants = [fake_db.get("tenants", tid)["fields"] for tid in res["tenant_ids"]]
    assert [t["Name"] for t in tenants] == ["Tom Tenant", "Tina Tenant"]  # lead first
    assert all(t["Property Id"] == [res["property_id"]] for t in tenants)
    assert all(t["Referencing_Status"] == "Imported" for t in tenants)

    # Provenance is readable back off the property.
    subs = [fake_db.get("submissions", sid)["fields"] for sid in pf["Submissions"]]
    assert [x["Form Name"] for x in subs] == [IMPORT_FORM_NAME]
    assert was_imported(res["property_id"]) is True

    # One audit row per gate passed, 2 through 8.
    log = fake_db.rows("gate_log")
    assert sorted(int(r["fields"]["To_Stage"]) for r in log) == list(range(2, 9))
    assert {r["fields"]["Result"] for r in log} == {"Passed"}

    # Live side-effects: financials plus the diary the TA-signed webhook
    # would have scheduled (S13 review, TDS countdown, cert renewals).
    assert len(fake_db.rows("financials")) == 1
    assert sorted(d["fields"]["Diary_Type"] for d in fake_db.rows("diary")) == [
        "EICR Renewal", "Gas Cert Renewal", "Rent Review S13", "TDS 30-Day Countdown",
    ]


@pytest.mark.asyncio
async def test_missing_signature_stops_at_that_gate_without_side_effects(fake_db):
    res = await handle_import(ImportTenancyInput(**{**_full_evidence(), "ta_tenants_signed": False}))

    assert res["is_live"] is False
    assert (res["stage_reached"], res["blocked_at"]) == (6, 7)
    assert any("not been signed by all tenants" in b for b in res["blockers"])
    pf = fake_db.get("properties", res["property_id"])["fields"]
    assert pf["Stage"] == [fake_db.stage_id(6)]
    assert pf["Gate Status"] == "Blocked"
    # Financials and the renewal diary only exist for a tenancy that is Live.
    assert fake_db.rows("financials") == [] and fake_db.rows("diary") == []


@pytest.mark.asyncio
async def test_bare_import_stops_at_compliance_and_reports_every_gap(fake_db):
    res = await handle_import(ImportTenancyInput(**BASE))

    assert (res["stage_reached"], res["blocked_at"]) == (2, 3)
    joined = " ".join(res["blockers"])
    for cert in ("gas safety certificate", "EPC", "EICR"):
        assert cert in joined
    assert "Terms & Conditions" in joined
    assert res["compliance"]["warnings"] or res["compliance"]["actions"]


@pytest.mark.asyncio
async def test_failure_part_way_leaves_nothing_behind(fake_db):
    # Property, landlord and the lead tenant are written before this fires.
    fake_db.fail_create = lambda table, fields: (
        table == "tenants" and fields.get("Name") == "Tina Tenant"
    )

    with pytest.raises(RuntimeError, match="injected failure"):
        await handle_import(ImportTenancyInput(**_full_evidence()))

    for table in ("properties", "landlords", "tenants", "submissions", "gate_log"):
        assert fake_db.rows(table) == [], table
    assert fake_db.link_count() == 0


@pytest.mark.asyncio
async def test_gate_walk_error_is_reported_not_raised(fake_db, monkeypatch):
    real = pg_import.evaluate_gate

    async def flaky(property_id, stage, **kw):
        if stage == 5:
            raise ConnectionError("database went away")
        return await real(property_id, stage, **kw)
    monkeypatch.setattr(pg_import, "evaluate_gate", flaky)

    res = await handle_import(ImportTenancyInput(**_full_evidence()))

    # The rows are consistent, so they stay; the agent is told how to resume
    # rather than handed a 500 that invites a duplicate import.
    assert (res["stage_reached"], res["blocked_at"]) == (4, 5)
    assert "Re-evaluate gate" in res["blockers"][0]
    assert "ConnectionError" in res["blockers"][0]
    assert len(fake_db.rows("properties")) == 1
    assert res["is_live"] is False
