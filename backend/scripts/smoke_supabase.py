"""End-to-end smoke test of the Supabase data layer against a REAL database.

Drives the actual handlers (PG_01 take-on → gate → PG_03 offer → accept →
referencing → scheduler → payments → cascade delete) through the supabase
client, asserting the link symmetry, lookups and Airtable-shape conventions
the app depends on. Run it whenever the schema or the adapter changes:

    # start the dev database (schema auto-applied on first boot)
    docker compose -f docker-compose.dev.yml up -d db

    # from backend/ — SUPABASE_DB_URL in .env must point at the database
    python -m scripts.smoke_supabase

Safe to re-run: everything it creates is deleted at the end (the final step
IS the cascade-delete check). Exits non-zero on the first failed assertion.

SMTP / DocuSeal / Paragon are not required — with no credentials configured
those clients log + degrade exactly as in dev.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta

# Windows consoles default to cp1252 — keep the arrows/ticks printable.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Force mock signing + deterministic behaviour regardless of the local .env.
import os
os.environ.setdefault("APP_ENV", "test")

from app.db import supabase_client as at  # noqa: E402


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "ok  " if ok else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        sys.exit(1)


async def main() -> None:
    from app.handlers.pg00_gate import evaluate_gate
    from app.handlers.pg01_takeon import handle_takeon
    from app.handlers.pg03_offer import handle_offer
    from app.handlers.pg06_scheduler import run_scheduler
    from app.models.common import OfferInput, PropertyTakeonInput
    from app.services.offers import accept_offer, offers_for_property
    from app.services.sent_documents import record_sent, update_status_by_envelope

    # ------------------------------------------------------------ PG_01 take-on
    res = await handle_takeon(PropertyTakeonInput(
        address="1 Smoke Test Mews, London",
        post_code="W8 5LS",
        landlord_full_name="Smoke Landlord",
        landlord_email="smoke-landlord@example.com",
        send_admin_form=False,
        asking_rent_pcm=2000,
        rent_frequency="Monthly",
    ))
    pid, llid = res["property_id"], res["landlord_id"]
    check("PG_01 created property + landlord", bool(pid and llid))
    check("PG_01 gate advanced to stage 2", res["gate"]["advanced"] is True, str(res["gate"]))

    prop = at.get(at.TableNames.PROPERTIES, pid, fresh=True)
    pf = prop["fields"]
    check("tenancy type derived", pf.get("Tenancy Type") == "APT", str(pf.get("Tenancy Type")))
    check("annual rent (trailing-space field)", pf.get("Annual Rent ") == 24000, str(pf.get("Annual Rent ")))
    check("landlord linked on property", pf.get("Landlords") == [llid], str(pf.get("Landlords")))
    check("Stage_Order lookup == 2", pf.get("Stage_Order") == 2, str(pf.get("Stage_Order")))
    ll = at.get(at.TableNames.LANDLORDS, llid, fresh=True)
    check("reverse link Landlords.Properties", ll["fields"].get("Properties") == [pid],
          str(ll["fields"].get("Properties")))
    check("submission audit row linked", len(pf.get("Submissions") or []) == 1)
    check("createdTime present", bool(prop.get("createdTime")))

    # ------------------------------------------------- stage 2→3 (compliance)
    at.update(at.TableNames.PROPERTIES, pid, {
        "Gas_Cert_Status": "On File",
        "EPC_Status": "On File",
        "EICR_Status": "On File",
        "EPC Rating ": "C",
        "Gas Certificates Expiry": (date.today() + timedelta(days=200)).isoformat(),
        "EICR Expiry": (date.today() + timedelta(days=400)).isoformat(),
        "TC_Signed": True,
    })
    gate = await evaluate_gate(pid, target_stage=3, silent=True)
    check("gate 2→3 advanced", gate.advanced, "; ".join(gate.failures))
    check("gate log written", len(at.get(at.TableNames.PROPERTIES, pid, fresh=True)
                                  ["fields"].get("Gate_Log") or []) >= 2)

    # --------------------------------------------------------------- PG_03 offer
    offer_res = await handle_offer(pid, OfferInput(
        tenant_full_name="Smoke Tenant",
        tenant_email="smoke-tenant@example.com",
        start_date=date.today() + timedelta(days=30),
        monthly_rent=2000.0,
        deposit_amount=2307.0,
        holding_deposit=461.0,
        instruct_paragon=False,
        anti_discrimination_confirmed=True,
    ))
    tid, oid = offer_res["tenant_id"], offer_res["offer_id"]
    check("PG_03 created tenant + offer", bool(tid and oid))

    pf = at.get(at.TableNames.PROPERTIES, pid, fresh=True)["fields"]
    check("offer reverse-linked on property", oid in (pf.get("Offers") or []), str(pf.get("Offers")))
    check("tenant NOT yet linked (pre-acceptance)", not pf.get("Tenant"), str(pf.get("Tenant")))
    offers = offers_for_property(pid)
    check("offers_for_property finds it", [o["id"] for o in offers] == [oid])
    check("offer is Pending", offers[0]["fields"].get("Status") == "Pending")
    tf = at.get(at.TableNames.TENANTS, tid, fresh=True)["fields"]
    check("tenant reverse link Property Id", tf.get("Property Id") == [pid], str(tf.get("Property Id")))

    # search() structured filters against live data
    found = at.find_first(at.TableNames.TENANTS, at.eq("Tenant Email", "smoke-tenant@example.com"), fresh=True)
    check("find_first by Tenant Email", bool(found) and found["id"] == tid)

    # ------------------------------------------------------------- accept offer
    acc = await accept_offer(oid, source="smoke")
    check("offer accepted", acc["status"] == "Accepted")
    pf = at.get(at.TableNames.PROPERTIES, pid, fresh=True)["fields"]
    check("tenant linked after acceptance", pf.get("Tenant") == [tid], str(pf.get("Tenant")))
    check("LL_Offer_Accepted set", pf.get("LL_Offer_Accepted") is True)

    # --------------------------------------------------- referencing + gate 5→6
    at.update(at.TableNames.TENANTS, tid, {"Referencing_Status": "Pass", "Referencing_Recorded": True})
    gate = await evaluate_gate(pid, target_stage=6, silent=True)
    check("gate 5→6 advanced after referencing", gate.advanced, "; ".join(gate.failures))
    check("Stage_Order lookup == 6",
          at.get(at.TableNames.PROPERTIES, pid, fresh=True)["fields"].get("Stage_Order") == 6)

    # ------------------------------------------------------------ sent documents
    sd_id = record_sent(property_id=pid, doc_id="tpl_01", doc_name="Smoke Letter",
                        stage=2, channel="Sign", recipients=["smoke-landlord@example.com"],
                        envelope_id="env-smoke-1", sent_by="smoke", status="Sent")
    check("sent_documents row created", bool(sd_id))
    check("status flip by envelope id", update_status_by_envelope("env-smoke-1", "Signed", completed=True))
    sd = at.get(at.TableNames.SENT_DOCUMENTS, sd_id, fresh=True)["fields"]
    check("sent doc Signed + completed", sd.get("Status") == "Signed" and bool(sd.get("Completed Date")))

    # ------------------------------------------------------------- PG_06 diary
    at.create(at.TableNames.DIARY, {
        "Diary_Type": "Reminder",
        "Property": [pid],
        "Diary Date": date.today().isoformat(),
        "Alert_Date": (date.today() - timedelta(days=1)).isoformat(),
        "Alert_Message": "Smoke diary alert",
        "Fired": False,
    })
    sched = await run_scheduler()
    check("scheduler fired the due alert", sched["fired"] >= 1, str(sched))

    # ---------------------------------------------------------------- payments
    pay = at.create(at.TableNames.PAYMENTS, {
        "property_id": pid, "tenant_id": tid, "offer_id": oid,
        "payment_type": "holding_deposit", "amount": 461.0,
        "currency": "gbp", "status": "pending", "description": "Smoke holding deposit",
        "metadata": {"source": "smoke"},
    })
    check("payment row created", bool(pay["id"]))
    rows = at.search(at.TableNames.PAYMENTS, at.eq("property_id", pid), fresh=True)
    check("payment searchable by property", len(rows) == 1 and rows[0]["fields"]["amount"] == 461)

    # ------------------------------------------------------- cascade delete
    # Mirrors routers/properties.delete_property: delete children, then the
    # property; landlord goes too since this was their only property.
    for tbl, ids in [
        (at.TableNames.TENANTS, pf.get("Tenant") or []),
        (at.TableNames.OFFERS, [oid]),
        (at.TableNames.DIARY, at.get(at.TableNames.PROPERTIES, pid, fresh=True)["fields"].get("Diary") or []),
        (at.TableNames.GATE_LOG, at.get(at.TableNames.PROPERTIES, pid, fresh=True)["fields"].get("Gate_Log") or []),
        (at.TableNames.SUBMISSIONS, at.get(at.TableNames.PROPERTIES, pid, fresh=True)["fields"].get("Submissions") or []),
        (at.TableNames.SENT_DOCUMENTS, [sd_id]),
        (at.TableNames.PAYMENTS, [pay["id"]]),
    ]:
        for rid in ids:
            at.delete(tbl, rid)
    at.delete(at.TableNames.LANDLORDS, llid)
    at.delete(at.TableNames.PROPERTIES, pid)
    try:
        at.get(at.TableNames.PROPERTIES, pid, fresh=True)
        check("property gone after delete", False)
    except Exception:
        check("property gone after delete", True)

    print("\nAll smoke checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
