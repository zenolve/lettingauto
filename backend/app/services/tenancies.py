"""End a tenancy and re-let the property (PG_RL, migration 005).

A property row carries one tenancy at a time: the signatures, deposit, served
flags, dates and the accepted tenants sit beside the landlord, the
certificates and the terms of business, and the stage is derived from those
fields. Letting the same property again therefore works in two steps:

1. **End tenancy** (stage 8 -> 9) records the end date; ``reopen_tenancy``
   takes it back while nothing else has happened.
2. **Re-let** (stage 9 -> Offer) archives the tenancy into ``tenancies`` - who,
   when, the terms, and a snapshot of every tenancy field - then clears those
   fields and cancels the tenancy's pending diary alerts. Property-level data
   stays: landlord, certificates, EPC, licences, insurance, consents and the
   signed terms of business, which already cover later tenancies ("Tenant"
   includes anyone subsequently taking a tenancy). The stage is then derived
   as usual - Offer, or earlier if a certificate has expired in the meantime.

A re-let is a new tenancy and is charged like one: ``start_relet`` opens a
pay-first checkout when billing is on, and ``billing.mark_paid_and_fulfill``
calls ``perform_relet`` once the fee clears.

What stays readable afterwards: tenant rows (via ``Tenants."Property Id"``),
offers, sent documents, gate log, diary and compliance records. Anything
tenancy-related created before ``Tenancy Cycle Started At`` belongs to an
archived tenancy (see ``belongs_to_previous_tenancy``).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Optional

from app.core.logger import get_logger
from app.db import supabase_client as at
from app.services.stages import derive_stage

logger = get_logger(__name__)

# Every property field that belongs to a tenancy, and the value a re-let resets
# it to. Anything not listed is about the property and carries over.
TENANCY_FIELDS: dict[str, Any] = {
    "LL_Offer_Accepted": False,
    "Anti_Discrimination_Confirmed": False,
    "Anti_Discrimination_Confirmed_Date": None,
    "Holding_Deposit_Deadline": None,
    "TA_LL_Signed": False,
    "TA_TT_Signed": False,
    "TDS Cert On File": False,
    "Deposit Registered": False,
    "Deposit Registration Date": None,
    "Deposit": None,
    "funds_cleared": False,
    "Works_Signed_Off": False,
    "How_To_Rent_Served": False,
    "Gas_Cert_Served": False,
    "EPC_Served": False,
    "EICR_Served": False,
    "TDS_Info_Served": False,
    "RRA_Sheet_Served": False,
    "RRA_sheet_served_date": None,
    "Tenancy Start Date": None,
    "Tenancy Expiry Date": None,
    "Checkin_Date": None,
    "Checkout_Date": None,
    "Inventory_Clerk": None,
}

# Diary alerts that only make sense for the tenancy being archived. Certificate
# renewals and the landlord's tax certificate are about the property and stay.
TENANCY_DIARY_TYPES = frozenset({
    "Rent Review S13", "TDS 30-Day Countdown", "Tenancy Expiry Warning",
    "RTR Followup",                       # the outgoing tenant's visa follow-up
    "Reminder",                           # offer chase for this let
    "Gas Cert Re-serve", "EICR Re-serve",  # owed to the outgoing tenant
})

# From TA signing onwards a new offer would inherit the current tenancy's
# signatures, deposit and served flags.
LOCKED_FROM_STAGE = 7

# Documents from Offer onwards belong to a tenancy; take-on, compliance and
# marketing documents (e.g. the landlord's terms of business) are the property's.
FIRST_TENANCY_STAGE = 4


class TenancyStateError(ValueError):
    """The property isn't at the stage this action needs (routers -> 409)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _today() -> str:
    return date.today().isoformat()


def _ts(value: Any) -> Optional[datetime]:
    """Parse a stored timestamp; ISO strings from Postgres and the adapter."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _fields(property_id: str) -> dict:
    return at.get(at.TableNames.PROPERTIES, property_id, fresh=True).get("fields", {})


def _stage_link(order: int) -> dict:
    from app.handlers.pg00_gate import find_stage_by_order  # noqa: PLC0415 — avoid load cycle
    rec = find_stage_by_order(order)
    return {"Stage": [rec["id"]]} if rec else {}


def _audit(property_id: str, form_name: str, data: dict) -> None:
    try:
        at.create(at.TableNames.SUBMISSIONS, {
            "Form Name": form_name,
            "Property": [property_id],
            "Submitted Date": _today(),
            "JSON Data": json.dumps(data, default=str),
        })
    except Exception as e:  # noqa: BLE001 — the audit row must not undo the action
        logger.warning("tenancies.audit_failed property=%s form=%s err=%s", property_id, form_name, e)


def cycle_started_at(fields: dict) -> Optional[datetime]:
    """When the property's current tenancy cycle began (None: its first)."""
    return _ts(fields.get("Tenancy Cycle Started At"))


def belongs_to_previous_tenancy(created: Any, cycle_start: Optional[datetime]) -> bool:
    """True when a record was created before the current tenancy cycle."""
    when = _ts(created)
    return bool(cycle_start and when and when < cycle_start)


def ensure_no_tenancy_in_progress(property_id: str, action: str) -> None:
    """Refuse an offer action once a tenancy agreement is being signed or is
    live: a new offer would inherit that tenancy's signatures and records."""
    stage = derive_stage(_fields(property_id))
    if stage < LOCKED_FROM_STAGE:
        return
    why = {
        7: "a tenancy agreement is already being signed for this property",
        8: "this property has a live tenancy - end it and re-let the property first",
        9: "the tenancy has ended - re-let the property first",
    }.get(stage, f"the property is at stage {stage}")
    raise TenancyStateError(f"'{action}' isn't possible: {why}.")


# ---------------------------------------------------------------------------
# End / reopen
# ---------------------------------------------------------------------------
def end_tenancy(property_id: str, end_date: date, *, by: str) -> dict:
    f = _fields(property_id)
    stage = derive_stage(f)
    if stage != 8:
        raise TenancyStateError(f"Only a live tenancy can be ended - this property is at stage {stage}.")
    started = f.get("Tenancy Start Date")
    if started and end_date.isoformat() < str(started):
        raise TenancyStateError(f"The end date can't be before the tenancy started ({started}).")
    at.update(at.TableNames.PROPERTIES, property_id, {
        "Tenancy Ended Date": end_date.isoformat(),
        "Stage changed at": _today(),
        **_stage_link(9),
    })
    _audit(property_id, "PG_RL End tenancy", {"end_date": end_date.isoformat(), "by": by})
    logger.info("tenancies.ended property=%s end=%s by=%s", property_id, end_date, by)
    return {"property_id": property_id, "stage": 9, "ended_on": end_date.isoformat()}


def reopen_tenancy(property_id: str, *, by: str) -> dict:
    """Undo "End tenancy" - only while the property is still at stage 9."""
    f = _fields(property_id)
    if derive_stage(f) != 9:
        raise TenancyStateError("Only an ended tenancy that hasn't been re-let can be reopened.")
    at.update(at.TableNames.PROPERTIES, property_id, {"Tenancy Ended Date": None, "Stage changed at": _today()})
    stage = derive_stage(_fields(property_id))
    link = _stage_link(stage)
    if link:
        at.update(at.TableNames.PROPERTIES, property_id, link)
    _audit(property_id, "PG_RL Reopen tenancy", {"ended_on_was": f.get("Tenancy Ended Date"), "by": by})
    return {"property_id": property_id, "stage": stage}


# ---------------------------------------------------------------------------
# Re-let
# ---------------------------------------------------------------------------
def _tenancy_rows(property_id: str) -> list[dict]:
    rows = at.search(at.TableNames.TENANCIES, at.eq("Property ID", property_id), fresh=True)
    rows.sort(key=lambda r: r.get("fields", {}).get("Sequence") or 0)
    return rows


def _accepted_offer(f: dict, tenant_ids: list[str]) -> Optional[dict]:
    best = None
    for oid in f.get("Offers") or []:
        try:
            offer = at.get(at.TableNames.OFFERS, oid)
        except Exception:  # noqa: BLE001
            continue
        of = offer.get("fields", {})
        if of.get("Status") != "Accepted":
            continue
        if tenant_ids and set(of.get("Tenants") or []) != set(tenant_ids):
            continue
        if best is None or (offer.get("createdTime") or "") > (best.get("createdTime") or ""):
            best = offer
    return best


def _archive(property_id: str, f: dict, *, by: str) -> dict:
    """Write the ``tenancies`` row for the tenancy that is ending.

    Idempotent per tenancy: an archive for this same cycle (same cycle start,
    same end date) is reused, so retrying a re-let that failed after archiving
    does not record the tenancy twice.
    """
    existing = _tenancy_rows(property_id)
    cycle = f.get("Tenancy Cycle Started At")
    for row in existing:
        rf = row.get("fields", {})
        if (rf.get("End Date") == f.get("Tenancy Ended Date")
                and (rf.get("Snapshot") or {}).get("cycle_started_at") == cycle):
            return row

    tenant_ids = list(f.get("Tenant") or [])
    tenants = []
    for tid in tenant_ids:
        try:
            tenants.append(at.get(at.TableNames.TENANTS, tid).get("fields", {}))
        except Exception:  # noqa: BLE001
            continue
    lead = tenants[0] if tenants else {}
    offer = _accepted_offer(f, tenant_ids)
    of = (offer or {}).get("fields", {})

    snapshot = {
        "fields": {k: f.get(k) for k in TENANCY_FIELDS},
        "tenant_ids": tenant_ids,
        "checklist_ids": list(f.get("Tenancy Checklist") or []),
        "accepted_offer_id": (offer or {}).get("id"),
        "cycle_started_at": cycle,           # None for the property's first tenancy
        "ended_on": f.get("Tenancy Ended Date"),
    }
    names = ", ".join(t.get("Name") for t in tenants if t.get("Name"))
    fields = {
        "Property ID": property_id,
        "Sequence": len(existing) + 1,
        "Tenant Names": names or None,
        "Start Date": f.get("Tenancy Start Date") or lead.get("Start Date"),
        "End Date": f.get("Tenancy Ended Date"),
        "Rent": lead.get("Amount") or of.get("Offered Rent"),
        "Rent Frequency": lead.get("Rent_Frequency") or of.get("Rent Frequency") or f.get("Rent Frequency"),
        "Deposit": f.get("Deposit") or lead.get("Deposit Amount") or of.get("Deposit"),
        "Tenancy Type": f.get("Tenancy Type"),
        "Snapshot": snapshot,
        "Archived By": by,
    }
    return at.create(at.TableNames.TENANCIES, {k: v for k, v in fields.items() if v is not None})


def _cancel_tenancy_diary(f: dict) -> int:
    """Close the archived tenancy's alerts that haven't fired yet.

    Marked fired with a note rather than deleted, so the diary still shows what
    was scheduled and why it stopped.
    """
    cancelled = 0
    for did in f.get("Diary") or []:
        try:
            d = at.get(at.TableNames.DIARY, did).get("fields", {})
        except Exception:  # noqa: BLE001
            continue
        if d.get("Fired") or d.get("Diary_Type") not in TENANCY_DIARY_TYPES:
            continue
        at.update(at.TableNames.DIARY, did, {
            "Fired": True,
            "Fired_Date": _today(),
            "Alert_Message": f"[Cancelled - tenancy ended] {d.get('Alert_Message') or ''}".strip(),
        })
        cancelled += 1
    return cancelled


def perform_relet(property_id: str, *, by: str) -> dict:
    """Archive the ended tenancy and open the property for the next one.

    Payment-agnostic, like take-on's handler: billing decides *whether* this
    runs; this decides *what* happens.
    """
    f = _fields(property_id)
    stage = derive_stage(f)
    if stage != 9:
        raise TenancyStateError(
            f"Only an ended tenancy can be re-let - end it first. This property is at stage {stage}."
        )
    tenancy = _archive(property_id, f, by=by)
    cancelled = _cancel_tenancy_diary(f)

    at.update(at.TableNames.PROPERTIES, property_id, {
        **TENANCY_FIELDS,
        "Tenant": [],
        "Tenancy Checklist": [],
        "Tenancy Ended Date": None,
        "Tenancy Cycle Started At": datetime.now(timezone.utc).isoformat(),
        "Gate Status": "Clear",
        "Gate Block Reason": "",
        "Stage changed at": _today(),
    })
    new_stage = derive_stage(_fields(property_id))
    link = _stage_link(new_stage)
    if link:
        at.update(at.TableNames.PROPERTIES, property_id, link)

    sequence = tenancy.get("fields", {}).get("Sequence")
    _audit(property_id, "PG_RL Re-let", {
        "tenancy_id": tenancy["id"], "sequence": sequence,
        "diary_cancelled": cancelled, "stage": new_stage, "by": by,
    })
    logger.info("tenancies.relet property=%s tenancy=%s seq=%s stage=%s diary_cancelled=%d",
                property_id, tenancy["id"], sequence, new_stage, cancelled)
    return {
        "property_id": property_id,
        "tenancy_id": tenancy["id"],
        "sequence": sequence,
        "stage": new_stage,
        "diary_cancelled": cancelled,
    }


async def start_relet(property_id: str, *, by: str) -> dict:
    """Re-let entry point: pay first when billing is on, else straight through.

    Never charges twice: an open checkout for this property is resumed, and a
    paid fee whose re-let failed is fulfilled again without a new charge.
    """
    from app.services import billing  # noqa: PLC0415 — avoid load cycle

    f = _fields(property_id)
    stage = derive_stage(f)
    if stage != 9:
        raise TenancyStateError(
            f"Only an ended tenancy can be re-let - end it first. This property is at stage {stage}."
        )
    agency_id = at.current_agency_id()
    if not (billing.billing_enabled() and agency_id):
        return {"payment_required": False, "relet": perform_relet(property_id, by=by)}

    open_pay, paid_unfulfilled = billing.relet_payments(property_id)
    if paid_unfulfilled:
        result = await billing.fulfil_relet(paid_unfulfilled)
        if result is None:
            raise TenancyStateError(
                "The re-let fee was paid but re-letting failed again - contact support with payment "
                f"reference {paid_unfulfilled['id']}. You have not been charged twice."
            )
        return {"payment_required": False, "relet": result, "already_paid": True}
    if open_pay:
        state = billing.checkout_state(open_pay)
        if state == "paid":
            # Paid, but neither the webhook nor the success page has fulfilled it yet.
            await billing.mark_paid_and_fulfill(open_pay)
            return {"payment_required": False, "already_paid": True,
                    "relet": {"property_id": property_id, "stage": derive_stage(_fields(property_id))}}
        if state in ("open", "unknown"):
            # "unknown" (Stripe unreachable) resumes too: opening a second
            # checkout could charge twice for the same re-let.
            meta = open_pay.get("fields", {}).get("metadata") or {}
            return {"payment_required": True, "payment_id": open_pay["id"],
                    "checkout_url": meta.get("checkout_url"), "resumed": True}
        at.update(at.TableNames.PAYMENTS, open_pay["id"], {"status": "cancelled"})  # expired

    intent = billing.create_relet_intent(agency_id, property_id, f.get("Address") or "", requested_by=by)
    return {"payment_required": True, **intent}


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
def history(property_id: str) -> list[dict]:
    """Archived tenancies, newest first, each with the documents sent during it."""
    from app.services import sent_documents as sd  # noqa: PLC0415 — avoid load cycle

    rows = _tenancy_rows(property_id)
    sent = [r for r in sd.list_for_property(property_id) if (r.get("stage") or 0) >= FIRST_TENANCY_STAGE]
    out: list[dict] = []
    for row in rows:
        rf = row.get("fields", {})
        snap = rf.get("Snapshot") or {}
        began = _ts(snap.get("cycle_started_at"))
        archived = _ts(row.get("createdTime"))
        docs = [
            d for d in sent
            if (when := _ts(d.get("sent_at"))) is not None
            and (began is None or when >= began)
            and (archived is None or when < archived)
        ]
        out.append({
            "id": row["id"],
            "sequence": rf.get("Sequence"),
            "tenant_names": rf.get("Tenant Names"),
            "start_date": rf.get("Start Date"),
            "end_date": rf.get("End Date"),
            "rent": rf.get("Rent"),
            "rent_frequency": rf.get("Rent Frequency"),
            "deposit": rf.get("Deposit"),
            "tenancy_type": rf.get("Tenancy Type"),
            "archived_at": row.get("createdTime"),
            "archived_by": rf.get("Archived By"),
            "documents": docs,
        })
    out.sort(key=lambda t: t.get("sequence") or 0, reverse=True)
    return out
