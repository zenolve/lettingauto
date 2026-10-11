"""Ending a tenancy and re-letting the property (PG_RL, migration 005).

The property row carries one tenancy at a time, so a re-let has to archive
the tenancy, clear exactly the tenancy fields, and leave everything that
belongs to the property - landlord, certificates, signed terms of business -
in place. These drive the real services and routes through the in-memory
adapter; Stripe is stubbed.
"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.auth import Agent
from app.db import supabase_client as at
from app.routers import forms
from app.routers import offers as offers_router
from app.services import billing, offers as offers_svc, sent_documents as sd, tenancies
from app.services.merge_fields import _resolve_tenant
from app.services.stages import derive_stage

AGENT = Agent(email="agent@example.com")
LONG_AGO = datetime(2025, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def live(fake_db):
    """A live tenancy as the pipeline leaves it: landlord, certificates, signed
    terms of business, an accepted offer, two tenants, signed and served."""
    far = (date.today() + timedelta(days=300)).isoformat()
    ll = fake_db.create("landlords", {"Full Name": "Lara Landlord", "Email Address": "lara@example.com"})["id"]
    pid = fake_db.create("properties", {
        "Address": "5 Relet Road", "Tenancy Type": "APT", "Rent Frequency": "Monthly",
        "Annual Rent ": 18000, "Landlords": [ll],
        "Gas_Cert_Status": "On File", "EPC_Status": "On File", "EICR_Status": "On File",
        "Gas Certificates Expiry": far, "EICR Expiry": far, "EPC Rating ": "C",
        "TC_Signed": True, "LL_Offer_Accepted": True, "Anti_Discrimination_Confirmed": True,
        "TA_LL_Signed": True, "TA_TT_Signed": True, "TDS Cert On File": True,
        "Deposit Registered": True, "Deposit Registration Date": "2025-01-10", "Deposit": 1700,
        "funds_cleared": True, "Works_Signed_Off": True,
        "How_To_Rent_Served": True, "Gas_Cert_Served": True, "EPC_Served": True,
        "EICR_Served": True, "TDS_Info_Served": True, "RRA_Sheet_Served": True,
        "Tenancy Start Date": "2025-01-01", "Tenancy Expiry Date": "2026-12-31",
    })["id"]
    t1 = fake_db.create("tenants", {"Name": "Tom Tenant", "Tenant Email": "tom@example.com",
                                    "Property Id": [pid], "Amount": 1500, "Rent_Frequency": "Monthly",
                                    "Start Date": "2025-01-01", "Deposit Amount": 1700})["id"]
    t2 = fake_db.create("tenants", {"Name": "Tina Tenant", "Property Id": [pid]})["id"]
    offer = fake_db.create("offers", {"Status": "Accepted", "Property": [pid], "Tenants": [t1, t2],
                                      "Offered Rent": 1500, "Rent Frequency": "Monthly", "Deposit": 1700})["id"]
    s13 = fake_db.create("diary", {"Diary_Type": "Rent Review S13", "Property": [pid],
                                   "Alert_Date": "2025-10-15", "Alert_Message": "Section 13 due", "Fired": False})["id"]
    gas = fake_db.create("diary", {"Diary_Type": "Gas Cert Renewal", "Property": [pid],
                                   "Alert_Date": far, "Alert_Message": "Gas renewal due", "Fired": False})["id"]
    old = fake_db.create("diary", {"Diary_Type": "TDS 30-Day Countdown", "Property": [pid],
                                   "Alert_Date": "2025-01-31", "Alert_Message": "Register deposit",
                                   "Fired": True, "Fired_Date": "2025-01-31"})["id"]
    keys = fake_db.create("checklist", {"Name": "Keys handed over"})["id"]
    fake_db.update("properties", pid, {"Tenant": [t1, t2], "Tenancy Checklist": [keys]})
    for rid in (ll, pid, t1, t2, offer, s13, gas, old, keys):
        fake_db.backdate(rid, LONG_AGO)
    return SimpleNamespace(pid=pid, landlord=ll, tenants=[t1, t2], offer=offer,
                           s13=s13, gas=gas, fired=old, checklist=keys)


def _f(fake_db, pid):
    return fake_db.get("properties", pid)["fields"]


def _ended(live, fake_db, on="2026-09-30"):
    tenancies.end_tenancy(live.pid, date.fromisoformat(on), by="agent@example.com")
    return live


# ------------------------------------------------------------------ end tenancy
def test_ending_a_live_tenancy_moves_it_to_stage_9(live, fake_db):
    out = tenancies.end_tenancy(live.pid, date(2026, 9, 30), by="agent@example.com")

    assert out["stage"] == 9
    f = _f(fake_db, live.pid)
    assert f["Tenancy Ended Date"] == "2026-09-30"
    assert derive_stage(f) == 9
    assert f["Stage"] == [fake_db.stage_id(9)]
    # Nothing about the tenancy is cleared yet - the agent may still undo.
    assert f["TA_LL_Signed"] is True and f["Tenant"] == live.tenants


def test_only_a_live_tenancy_can_be_ended_and_not_before_it_began(live, fake_db):
    with pytest.raises(tenancies.TenancyStateError, match="before the tenancy started"):
        tenancies.end_tenancy(live.pid, date(2024, 12, 31), by="a")
    fake_db.update("properties", live.pid, {"TA_TT_Signed": False})  # stage 7
    with pytest.raises(tenancies.TenancyStateError, match="Only a live tenancy"):
        tenancies.end_tenancy(live.pid, date(2026, 9, 30), by="a")


def test_reopen_takes_an_ended_tenancy_back_to_live(live, fake_db):
    _ended(live, fake_db)
    out = tenancies.reopen_tenancy(live.pid, by="a")

    assert out["stage"] == 8
    assert "Tenancy Ended Date" not in _f(fake_db, live.pid)
    with pytest.raises(tenancies.TenancyStateError):
        tenancies.reopen_tenancy(live.pid, by="a")      # nothing left to reopen


# ----------------------------------------------------------------------- re-let
def test_relet_archives_the_tenancy_and_opens_the_property_for_offers(live, fake_db):
    _ended(live, fake_db)
    out = tenancies.perform_relet(live.pid, by="agent@example.com")

    # Archived: who, when, terms, and every tenancy field as it stood.
    [arch] = fake_db.rows("tenancies")
    a = arch["fields"]
    assert (a["Sequence"], a["Tenant Names"], a["Start Date"], a["End Date"]) == (
        1, "Tom Tenant, Tina Tenant", "2025-01-01", "2026-09-30")
    assert (a["Rent"], a["Rent Frequency"], a["Deposit"], a["Tenancy Type"]) == (1500, "Monthly", 1700, "APT")
    snap = a["Snapshot"]
    assert snap["fields"]["TA_TT_Signed"] is True and snap["fields"]["Deposit"] == 1700
    assert snap["tenant_ids"] == live.tenants and snap["checklist_ids"] == [live.checklist]
    assert snap["accepted_offer_id"] == live.offer and snap["cycle_started_at"] is None

    f = _f(fake_db, live.pid)
    # Every tenancy field is back to its starting value...
    for field, reset in tenancies.TENANCY_FIELDS.items():
        assert f.get(field, reset if reset is not False else False) in (reset, None, False), field
    assert "Tenant" not in f and "Tenancy Checklist" not in f and "Tenancy Ended Date" not in f
    assert f["Tenancy Cycle Started At"]
    # ...and everything about the property carried over, the T&Cs included.
    assert f["TC_Signed"] is True and f["Landlords"] == [live.landlord]
    assert (f["Gas_Cert_Status"], f["EPC Rating "], f["Annual Rent "]) == ("On File", "C", 18000)

    assert out["stage"] == derive_stage(f) == 4
    assert f["Stage"] == [fake_db.stage_id(4)]

    # The tenancy's own pending alerts are closed with a note; the property's stay.
    s13 = fake_db.get("diary", live.s13)["fields"]
    assert s13["Fired"] is True and s13["Alert_Message"].startswith("[Cancelled - tenancy ended]")
    assert fake_db.get("diary", live.gas)["fields"]["Fired"] is False
    assert fake_db.get("diary", live.fired)["fields"]["Alert_Message"] == "Register deposit"
    assert out["diary_cancelled"] == 1

    # History survives: tenants keep their link to the property, the offer stays.
    assert fake_db.get("tenants", live.tenants[0])["fields"]["Property Id"] == [live.pid]
    assert fake_db.get("offers", live.offer)["fields"]["Status"] == "Accepted"


def test_relet_needs_an_ended_tenancy(live):
    with pytest.raises(tenancies.TenancyStateError, match="Only an ended tenancy"):
        tenancies.perform_relet(live.pid, by="a")


def test_each_relet_archives_the_next_tenancy(live, fake_db):
    _ended(live, fake_db)
    tenancies.perform_relet(live.pid, by="a")
    # The next tenancy runs its course and ends too.
    fake_db.update("properties", live.pid, {"Tenant": [live.tenants[1]], "TA_LL_Signed": True,
                                            "TA_TT_Signed": True, "Tenancy Start Date": "2026-11-01"})
    _ended(live, fake_db, on="2027-10-31")
    tenancies.perform_relet(live.pid, by="a")

    seqs = sorted(r["fields"]["Sequence"] for r in fake_db.rows("tenancies"))
    assert seqs == [1, 2]
    second = next(r for r in fake_db.rows("tenancies") if r["fields"]["Sequence"] == 2)["fields"]
    assert second["Snapshot"]["cycle_started_at"]       # began at the first re-let
    assert [t["sequence"] for t in tenancies.history(live.pid)] == [2, 1]


def test_a_relet_that_fails_part_way_does_not_archive_twice_on_retry(live, fake_db, monkeypatch):
    _ended(live, fake_db)
    real = tenancies._cancel_tenancy_diary
    monkeypatch.setattr(tenancies, "_cancel_tenancy_diary", lambda f: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        tenancies.perform_relet(live.pid, by="a")
    assert derive_stage(_f(fake_db, live.pid)) == 9          # nothing reset yet

    monkeypatch.setattr(tenancies, "_cancel_tenancy_diary", real)
    tenancies.perform_relet(live.pid, by="a")
    assert len(fake_db.rows("tenancies")) == 1


# ------------------------------------------------------------------ offer guard
@pytest.mark.parametrize("stage_fields,stage", [
    ({"TA_TT_Signed": False}, 7),
    ({}, 8),
    ({"Tenancy Ended Date": "2026-09-30"}, 9),
])
def test_no_new_offer_once_a_tenancy_is_signed_or_live(live, fake_db, stage_fields, stage):
    fake_db.update("properties", live.pid, stage_fields)
    assert derive_stage(_f(fake_db, live.pid)) == stage
    with pytest.raises(HTTPException) as exc:
        forms._require_no_tenancy_in_progress(live.pid, action="Record offer")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_a_late_offer_acceptance_cannot_land_on_a_live_tenancy(live, fake_db):
    late = fake_db.create("offers", {"Status": "Pending", "Property": [live.pid], "Tenants": [live.tenants[1]]})["id"]
    with pytest.raises(HTTPException) as exc:
        await offers_router.accept(late, _=AGENT)
    assert exc.value.status_code == 409
    assert _f(fake_db, live.pid)["Tenant"] == live.tenants          # untouched
    with pytest.raises(tenancies.TenancyStateError):                  # the webhook path too
        await offers_svc.accept_offer(late, source="docusign")


def test_after_relet_the_previous_tenancy_stays_out_of_the_new_one(live, fake_db):
    _ended(live, fake_db)
    tenancies.perform_relet(live.pid, by="a")
    forms._require_no_tenancy_in_progress(live.pid, action="Record offer")   # allowed again

    # The Offers panel shows only this tenancy's offers by default.
    assert offers_router.list_offers(live.pid, include_previous=False, _=AGENT)["offers"] == []
    previous = offers_router.list_offers(live.pid, include_previous=True, _=AGENT)["offers"]
    assert [o["previous_tenancy"] for o in previous] == [True]

    # Merge fields don't fall back to the previous tenancy's tenants...
    assert _resolve_tenant(_f(fake_db, live.pid)) == {}
    # ...but pick up the new applicant as soon as an offer is recorded.
    nina = fake_db.create("tenants", {"Name": "Nina New"})["id"]
    fake_db.create("offers", {"Status": "Pending", "Property": [live.pid], "Tenants": [nina]})
    assert _resolve_tenant(_f(fake_db, live.pid))["Name"] == "Nina New"


def test_documents_are_scoped_to_their_tenancy(live, fake_db):
    ta = sd.record_sent(property_id=live.pid, doc_id="common_law_ta", doc_name="Tenancy agreement",
                        stage=6, channel="Sign", envelope_id="env-ta")
    tcs = sd.record_sent(property_id=live.pid, doc_id="pg_tcs_2026", doc_name="Terms of business",
                         stage=2, channel="Sign", envelope_id="env-tcs")
    for rid in (ta, tcs):
        fake_db.backdate(rid, LONG_AGO)
    _ended(live, fake_db)
    tenancies.perform_relet(live.pid, by="a")

    rows = {r["submission_id"]: r for r in sd.list_for_property(live.pid)}
    assert rows[ta]["previous_tenancy"] is True      # the old tenant's agreement
    assert rows[tcs]["previous_tenancy"] is False    # the landlord's T&Cs carry over
    # The next agreement is a new document, not a revision of the old one...
    assert sd.current_version(live.pid, "common_law_ta") is None
    # ...while the T&Cs can still be revised in place.
    assert sd.current_version(live.pid, "pg_tcs_2026")["submission_id"] == tcs
    [hist] = tenancies.history(live.pid)
    assert [d["submission_id"] for d in hist["documents"]] == [ta]


# ---------------------------------------------------------------------- billing
class _FakeStripe:
    def __init__(self):
        self.sessions: list[dict] = []
        self.state = {"status": "open", "payment_status": "unpaid"}
        outer = self

        class Customer:
            @staticmethod
            def create(**kw):
                return {"id": "cus_test"}

        class Session:
            @staticmethod
            def create(**kw):
                outer.sessions.append(kw)
                n = len(outer.sessions)
                return {"id": f"cs_test_{n}", "url": f"https://checkout.test/{n}"}

            @staticmethod
            def retrieve(sid):
                return dict(outer.state)

        self.Customer = Customer
        self.checkout = SimpleNamespace(Session=Session)


@pytest.fixture
def paid_billing(fake_db, monkeypatch):
    stripe = _FakeStripe()
    monkeypatch.setattr(billing, "billing_enabled", lambda: True)
    monkeypatch.setattr(billing, "_stripe", lambda: stripe)
    agency = fake_db.create("agencies", {"name": "Test Lettings", "slug": "test-lettings"})["id"]
    token = at.set_agency_scope(agency)
    yield stripe
    at.reset_agency_scope(token)


@pytest.mark.asyncio
async def test_relet_with_billing_off_happens_straight_away(live, fake_db):
    _ended(live, fake_db)
    out = await tenancies.start_relet(live.pid, by="a")
    assert out["payment_required"] is False and out["relet"]["stage"] == 4
    assert fake_db.rows("payments") == []


@pytest.mark.asyncio
async def test_relet_is_charged_first_and_fulfilled_exactly_once(live, fake_db, paid_billing):
    _ended(live, fake_db)
    out = await tenancies.start_relet(live.pid, by="agent@example.com")

    assert out["payment_required"] is True and out["checkout_url"] == "https://checkout.test/1"
    [pay] = fake_db.rows("payments")
    pf = pay["fields"]
    assert (pf["status"], pf["payment_type"], pf["amount"]) == ("pending", "tenancy_setup_fee", 50)
    assert pf["property_id"] == live.pid and pf["metadata"]["relet"]["property_id"] == live.pid
    assert paid_billing.sessions[0]["metadata"]["kind"] == "tenancy_relet"
    assert "kind=relet" in paid_billing.sessions[0]["success_url"]
    assert derive_stage(_f(fake_db, live.pid)) == 9      # nothing happens before payment

    again = await tenancies.start_relet(live.pid, by="a")    # e.g. clicked twice
    assert again["resumed"] is True and len(paid_billing.sessions) == 1

    stale = fake_db.get("payments", pay["id"])
    assert await billing.mark_paid_and_fulfill(stale) == live.pid
    assert await billing.mark_paid_and_fulfill(stale) == live.pid   # the other path, late
    assert len(fake_db.rows("tenancies")) == 1
    assert derive_stage(_f(fake_db, live.pid)) == 4

    status = await forms.takeon_status(pay["id"], _=AGENT)
    assert (status["kind"], status["fulfilled"], status["property_id"]) == ("relet", True, live.pid)


@pytest.mark.asyncio
async def test_a_paid_relet_that_failed_is_retried_without_charging_again(live, fake_db, paid_billing, monkeypatch):
    _ended(live, fake_db)
    await tenancies.start_relet(live.pid, by="a")
    [pay] = fake_db.rows("payments")

    real = tenancies.perform_relet
    monkeypatch.setattr(tenancies, "perform_relet", lambda pid, by: 1 / 0)
    assert await billing.mark_paid_and_fulfill(fake_db.get("payments", pay["id"])) is None
    pf = fake_db.get("payments", pay["id"])["fields"]
    assert pf["status"] == "succeeded" and "fulfillment_error" in pf["metadata"]

    monkeypatch.setattr(tenancies, "perform_relet", real)
    out = await tenancies.start_relet(live.pid, by="a")
    assert out["already_paid"] is True and out["relet"]["stage"] == 4
    assert len(fake_db.rows("payments")) == 1 and len(paid_billing.sessions) == 1
    assert "fulfillment_error" not in fake_db.get("payments", pay["id"])["fields"]["metadata"]


@pytest.mark.asyncio
async def test_an_expired_checkout_is_replaced_and_a_paid_one_is_fulfilled(live, fake_db, paid_billing):
    _ended(live, fake_db)
    await tenancies.start_relet(live.pid, by="a")
    paid_billing.state = {"status": "expired", "payment_status": "unpaid"}
    fresh = await tenancies.start_relet(live.pid, by="a")
    assert fresh["checkout_url"] == "https://checkout.test/2"
    assert sorted(p["fields"]["status"] for p in fake_db.rows("payments")) == ["cancelled", "pending"]

    paid_billing.state = {"status": "complete", "payment_status": "paid"}
    done = await tenancies.start_relet(live.pid, by="a")   # webhook never arrived
    assert done["already_paid"] is True and derive_stage(_f(fake_db, live.pid)) == 4


def test_takeon_checkout_is_unchanged_by_the_shared_helper(fake_db, paid_billing):
    out = billing.create_takeon_intent(at.current_agency_id(), {"address": "9 New Street"})
    [kw] = paid_billing.sessions
    assert out["checkout_url"] == "https://checkout.test/1"
    assert kw["metadata"]["kind"] == "tenancy_setup" and kw["client_reference_id"] == out["payment_id"]
    assert kw["success_url"].endswith(f"/agent/takeon/complete?payment={out['payment_id']}")
    assert "/agent/properties/new?payment=cancelled" in kw["cancel_url"]
    assert kw["line_items"][0]["price_data"]["unit_amount"] == 5000
