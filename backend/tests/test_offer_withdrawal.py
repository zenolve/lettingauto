"""An accepted offer that falls through before move-in.

Withdrawing (or rejecting) the accepted offer used to roll back only the
tenant link and LL_Offer_Accepted. A tenancy agreement the landlord had
already signed stayed signed, so the next accepted offer jumped straight to
pre-move-in with the previous tenant's signature - and a deposit, How to Rent
or move-in record made for them carried over too. These drive close_offer and
the offer routes through the in-memory adapter.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core import signing
from app.core.auth import Agent
from app.handlers import pg00_gate
from app.routers import offers as offers_router
from app.services import offers as offers_svc, sent_documents as sd, tenancies
from app.services.stages import derive_stage

AGENT = Agent(email="agent@example.com")
LONG_AGO = datetime(2025, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def signing_stage(fake_db, monkeypatch):
    """Accepted offer, landlord has signed the agreement, tenant hasn't (stage 7)."""
    async def _quiet(*a, **k):
        return None
    monkeypatch.setattr(pg00_gate, "send_agent_summary", _quiet)
    monkeypatch.setattr(offers_svc, "email_lead_tenant", _quiet)
    voided: list[str] = []

    async def _void(envelope_id, reason):
        voided.append(envelope_id)
    monkeypatch.setattr(signing, "void_submission", _void)

    far = (date.today() + timedelta(days=300)).isoformat()
    pid = fake_db.create("properties", {
        "Address": "8 Fallthrough Lane", "TC_Signed": True,
        "Gas_Cert_Status": "On File", "EPC_Status": "On File", "EICR_Status": "On File",
        "Gas Certificates Expiry": far, "EICR Expiry": far,
        "Anti_Discrimination_Confirmed": True, "Works_Signed_Off": True,
        "LL_Offer_Accepted": True, "TA_LL_Signed": True, "TA_TT_Signed": False,
        "Holding_Deposit_Deadline": far, "Deposit": 1700, "Deposit Registered": True,
        "TDS Cert On File": True, "How_To_Rent_Served": True, "funds_cleared": True,
        "Tenancy Start Date": far,
    })["id"]
    tom = fake_db.create("tenants", {"Name": "Tom Tenant", "Property Id": [pid]})["id"]
    offer = fake_db.create("offers", {"Status": "Accepted", "Property": [pid], "Tenants": [tom]})["id"]
    keys = fake_db.create("checklist", {"Name": "References received"})["id"]
    rtr = fake_db.create("diary", {"Diary_Type": "RTR Followup", "Property": [pid],
                                   "Alert_Date": far, "Alert_Message": "Visa check", "Fired": False})["id"]
    gas = fake_db.create("diary", {"Diary_Type": "Gas Cert Renewal", "Property": [pid],
                                   "Alert_Date": far, "Alert_Message": "Gas renewal", "Fired": False})["id"]
    fake_db.update("properties", pid, {"Tenant": [tom], "Tenancy Checklist": [keys]})
    open_ta = sd.record_sent(property_id=pid, doc_id="common_law_ta", doc_name="Common Law Tenancy Agreement",
                             stage=6, channel="Sign", envelope_id="env-open")
    done_ta = sd.record_sent(property_id=pid, doc_id="common_law_ta", doc_name="Common Law Tenancy Agreement",
                             stage=6, channel="Sign", envelope_id="env-signed")
    sd.update_status_by_envelope("env-signed", "Signed", completed=True)
    for rid in (pid, tom, offer, keys, rtr, gas, open_ta, done_ta):
        fake_db.backdate(rid, LONG_AGO)
    assert derive_stage(fake_db.get("properties", pid)["fields"]) == 7
    return type("S", (), dict(pid=pid, tom=tom, offer=offer, rtr=rtr, gas=gas,
                              open_ta=open_ta, done_ta=done_ta, voided=voided))


def _f(fake_db, pid):
    return fake_db.get("properties", pid)["fields"]


@pytest.mark.asyncio
async def test_withdrawing_clears_the_signature_and_everything_done_for_that_tenant(signing_stage, fake_db):
    s = signing_stage
    out = await offers_svc.close_offer(s.offer, status="Withdrawn_By_Tenant", reason="Moved abroad")

    f = _f(fake_db, s.pid)
    for field in ("TA_LL_Signed", "LL_Offer_Accepted", "Deposit Registered", "TDS Cert On File",
                  "How_To_Rent_Served", "funds_cleared"):
        assert not f.get(field), field
    for field in ("Deposit", "Holding_Deposit_Deadline", "Tenancy Start Date", "Tenant", "Tenancy Checklist"):
        assert field not in f, field
    # The marketing round, the property's works and the landlord's terms stand.
    assert f["Anti_Discrimination_Confirmed"] is True and f["Works_Signed_Off"] is True
    assert f["TC_Signed"] is True and f["Gas_Cert_Status"] == "On File"

    assert derive_stage(f) == 4 and f["Stage"] == [fake_db.stage_id(4)]
    assert out["rolled_back_property"] is True
    assert "TA_LL_Signed" in out["unwound"]["cleared"] and "Deposit Registered" in out["unwound"]["cleared"]
    assert fake_db.get("offers", s.offer)["fields"]["Status"] == "Withdrawn_By_Tenant"


@pytest.mark.asyncio
async def test_the_next_accepted_offer_starts_at_signing_not_part_signed(signing_stage, fake_db):
    s = signing_stage
    await offers_svc.close_offer(s.offer, status="Withdrawn_By_Tenant")
    nina = fake_db.create("tenants", {"Name": "Nina Next"})["id"]
    nxt = fake_db.create("offers", {"Status": "Pending", "Property": [s.pid], "Tenants": [nina]})["id"]

    await offers_svc.accept_offer(nxt, source="agent")

    f = _f(fake_db, s.pid)
    assert f["Tenant"] == [nina]
    assert not f.get("TA_LL_Signed")
    assert derive_stage(f) == 6        # ready for the agreement - not stage 7 on an old signature


@pytest.mark.asyncio
async def test_an_agreement_still_out_for_signature_is_voided(signing_stage, fake_db):
    s = signing_stage
    out = await offers_svc.close_offer(s.offer, status="Withdrawn_By_Tenant")

    assert s.voided == ["env-open"]               # the signed one can't be, and isn't, touched
    assert out["unwound"]["voided"] == ["Common Law Tenancy Agreement"]
    assert sd.summarise(sd.get_sent(s.open_ta))["status"] == "Voided"
    assert sd.summarise(sd.get_sent(s.done_ta))["status"] == "Signed"


@pytest.mark.asyncio
async def test_a_void_the_provider_refuses_is_reported_and_the_withdrawal_still_completes(
        signing_stage, fake_db, monkeypatch):
    s = signing_stage

    async def _refuse(envelope_id, reason):
        raise RuntimeError("envelope already completed")
    monkeypatch.setattr(signing, "void_submission", _refuse)

    out = await offers_svc.close_offer(s.offer, status="Withdrawn_By_Tenant")

    assert out["unwound"]["voided"] == []
    assert "envelope already completed" in out["unwound"]["void_errors"][0]
    assert derive_stage(_f(fake_db, s.pid)) == 4


@pytest.mark.asyncio
async def test_landlord_rejection_after_acceptance_unwinds_the_same_way(signing_stage, fake_db):
    s = signing_stage
    out = await offers_router.reject(s.offer, body=None, _=AGENT)

    assert out["rolled_back_property"] is True
    assert not _f(fake_db, s.pid).get("TA_LL_Signed")


@pytest.mark.asyncio
async def test_a_live_tenancys_offer_cannot_be_withdrawn(signing_stage, fake_db):
    s = signing_stage
    fake_db.update("properties", s.pid, {"TA_TT_Signed": True})     # both signed: live
    before = dict(_f(fake_db, s.pid))

    with pytest.raises(tenancies.TenancyStateError, match="end the tenancy"):
        await offers_svc.close_offer(s.offer, status="Withdrawn_By_Tenant")
    with pytest.raises(HTTPException) as exc:
        await offers_router.withdraw(s.offer, body=None, _=AGENT)
    assert exc.value.status_code == 409

    assert fake_db.get("offers", s.offer)["fields"]["Status"] == "Accepted"
    assert _f(fake_db, s.pid) == before and s.voided == []


@pytest.mark.asyncio
async def test_withdrawing_before_any_signature_still_just_rolls_back(signing_stage, fake_db):
    s = signing_stage
    fake_db.update("properties", s.pid, {"TA_LL_Signed": False})     # stage 6
    out = await offers_svc.close_offer(s.offer, status="Withdrawn_By_Tenant")

    assert "TA_LL_Signed" not in out["unwound"]["cleared"]
    assert derive_stage(_f(fake_db, s.pid)) == 4


@pytest.mark.asyncio
async def test_closing_another_applicants_offer_leaves_the_tenancy_alone(signing_stage, fake_db):
    s = signing_stage
    rival = fake_db.create("offers", {"Status": "Pending", "Property": [s.pid],
                                      "Tenants": [fake_db.create("tenants", {"Name": "Rita Rival"})["id"]]})["id"]
    out = await offers_svc.close_offer(rival, status="Withdrawn_By_Tenant")

    assert out["rolled_back_property"] is False and "unwound" not in out
    f = _f(fake_db, s.pid)
    assert f["Tenant"] == [s.tom] and f["TA_LL_Signed"] is True and s.voided == []


@pytest.mark.asyncio
async def test_withdrawal_cancels_the_tenancys_pending_alerts_only(signing_stage, fake_db):
    s = signing_stage
    await offers_svc.close_offer(s.offer, status="Withdrawn_By_Tenant")

    rtr = fake_db.get("diary", s.rtr)["fields"]
    assert rtr["Fired"] is True and rtr["Alert_Message"].startswith("[Cancelled - tenancy ended]")
    assert fake_db.get("diary", s.gas)["fields"]["Fired"] is False
