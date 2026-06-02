"""Dashboard aggregation (entry-point metrics).

A single ``GET /api/dashboard`` endpoint that rolls up the whole portfolio in
one pass per table — no per-property fan-out. Powers the agent home page:
act-now counts, pipeline distribution, compliance posture, upcoming dates and
a portfolio summary.

Design notes / best practices:
- **One read per table.** Properties / Offers / Diary / Tenant are each fetched
  once; everything else is derived in-memory. No N+1 Airtable calls.
- **Graceful degradation.** A failure reading any secondary table yields an
  empty section rather than a 500 — the dashboard always renders.
- **Pure core.** ``_build_dashboard()`` holds the logic and is import-testable;
  the route is a thin auth wrapper.
- Stage derivation reuses ``properties._derive_stage_order_from_fields`` so the
  dashboard, the property list and the gate guard all agree on "what stage".
"""
from __future__ import annotations

import threading
import time
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.core.auth import Agent, require_agent
from app.core.logger import get_logger
from app.db import airtable_client as at
from app.routers.properties import _STAGE_NAMES, _derive_stage_order_from_fields
from app.services.derivations import parse_iso_date

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
logger = get_logger(__name__)

# --- tunable thresholds (days) ---------------------------------------------
EXPIRY_SOON_DAYS = 30      # "expiring soon" / act-now bucket
EXPIRY_RUNWAY_DAYS = 90    # how far ahead the cert runway looks
STALLED_DAYS = 14          # same stage longer than this = stalled
UPCOMING_DIARY_DAYS = 30   # agenda window
LIST_CAP = 50              # bound list payloads

# Airtable field-name quirks (trailing spaces are real in the live base).
F_ANNUAL_RENT = "Annual Rent "
F_EPC_RATING = "EPC Rating "

_CERTS = [
    ("Gas", "Gas_Cert_Status", "Gas Certificates Expiry"),
    ("EICR", "EICR_Status", "EICR Expiry"),
]


def _all_safe(table: str) -> list[dict]:
    try:
        return at.all_records(table)
    except Exception as e:  # noqa: BLE001
        logger.warning("dashboard.read_failed table=%s err=%s", table, e)
        return []


def classify_compliance(fields: dict, today: date) -> str:
    """Bucket a property's compliance into 'compliant' | 'expiring' | 'bad'.

    Pure function (no I/O) so it can be unit-tested.
      - bad      : a cert is Not Provided, an on-file cert has expired, or EPC is F/G
      - expiring : (not bad) a cert is still being arranged, or a gas/EICR cert
                   expires within EXPIRY_SOON_DAYS
      - compliant: everything on file and in date
    """
    epc = (fields.get(F_EPC_RATING) or "").strip().upper()
    statuses = [fields.get(k) for _, k, _ in _CERTS] + [fields.get("EPC_Status")]

    bad = epc in ("F", "G") or any(s == "Not Provided" for s in statuses)
    for _, status_key, exp_key in _CERTS:
        if fields.get(status_key) == "On File":
            exp = parse_iso_date(fields.get(exp_key))
            if exp and exp < today:
                bad = True
    if bad:
        return "bad"

    expiring = any(s == "Palace Gate Arranging" for s in statuses)
    for _, status_key, exp_key in _CERTS:
        if fields.get(status_key) == "On File":
            exp = parse_iso_date(fields.get(exp_key))
            if exp and 0 <= (exp - today).days <= EXPIRY_SOON_DAYS:
                expiring = True
    return "expiring" if expiring else "compliant"


def _build_dashboard() -> dict[str, Any]:
    today = date.today()
    props = _all_safe(at.TableNames.PROPERTIES)
    offers = _all_safe(at.TableNames.OFFERS)
    diary = _all_safe(at.TableNames.DIARY)
    tenants = _all_safe(at.TableNames.TENANTS)

    addr_by_pid = {p["id"]: p.get("fields", {}).get("Address", "") for p in props}

    by_stage = {i: 0 for i in range(1, 10)}
    blocked = pre_tenancy = active = ending = 0
    rent_roll_annual = 0.0
    hmo_unconfirmed = epc_fg = 0
    type_split: dict[str, int] = {}
    service_split: dict[str, int] = {}
    comp = {"compliant": 0, "expiring": 0, "bad": 0}
    expiry_runway: list[dict] = []
    certs_expiring_30 = 0
    stalled: list[dict] = []

    for p in props:
        f = p.get("fields", {})
        order = _derive_stage_order_from_fields(f)
        by_stage[order] += 1
        if order == 8:
            active += 1
        elif order == 9:
            ending += 1
        else:
            pre_tenancy += 1

        if f.get("Gate Status") == "Blocked":
            blocked += 1

        changed = parse_iso_date(f.get("Stage changed at"))
        if changed and order < 8:
            d = (today - changed).days
            if d > STALLED_DAYS:
                stalled.append({
                    "property_id": p["id"], "address": addr_by_pid.get(p["id"]),
                    "stage_order": order, "stage_name": _STAGE_NAMES.get(order), "days_stuck": d,
                })

        if (tt := f.get("Tenancy Type")):
            type_split[tt] = type_split.get(tt, 0) + 1
        if (sl := f.get("Service Level")):
            service_split[sl] = service_split.get(sl, 0) + 1

        if order == 8 and f.get(F_ANNUAL_RENT):
            try:
                rent_roll_annual += float(f.get(F_ANNUAL_RENT))
            except (TypeError, ValueError):
                pass

        if f.get("HMO_Flag") and not f.get("HMO_Licence_Confirmed"):
            hmo_unconfirmed += 1
        if (f.get(F_EPC_RATING) or "").strip().upper() in ("F", "G"):
            epc_fg += 1

        if order >= 2:  # compliance only applies once past take-on
            comp[classify_compliance(f, today)] += 1

        for cert, status_key, exp_key in _CERTS:
            if f.get(status_key) == "On File":
                exp = parse_iso_date(f.get(exp_key))
                if exp is None:
                    continue
                d_left = (exp - today).days
                if d_left <= EXPIRY_RUNWAY_DAYS:
                    expiry_runway.append({
                        "property_id": p["id"], "address": addr_by_pid.get(p["id"]),
                        "cert": cert, "expiry": exp.isoformat(), "days_left": d_left,
                    })
                    if 0 <= d_left <= EXPIRY_SOON_DAYS:
                        certs_expiring_30 += 1

    # --- offers ---
    offer_status: dict[str, int] = {}
    for o in offers:
        if (s := o.get("fields", {}).get("Status")):
            offer_status[s] = offer_status.get(s, 0) + 1

    # --- diary agenda + overdue ---
    agenda: list[dict] = []
    overdue = 0
    for drow in diary:
        df = drow.get("fields", {})
        if df.get("Fired"):
            continue
        ad = parse_iso_date(df.get("Alert_Date"))
        if ad is None:
            continue
        d_until = (ad - today).days
        pid = (df.get("Property") or [None])[0]
        if d_until < 0:
            overdue += 1
        elif d_until <= UPCOMING_DIARY_DAYS:
            agenda.append({
                "property_id": pid, "address": addr_by_pid.get(pid),
                "type": df.get("Diary_Type"), "alert_date": ad.isoformat(),
                "days_until": d_until, "message": df.get("Alert_Message"),
            })

    referencing_pending = sum(
        1 for t in tenants if t.get("fields", {}).get("Referencing_Status") == "Pending"
    )

    # sort + bound
    stalled.sort(key=lambda r: r["days_stuck"], reverse=True)
    expiry_runway.sort(key=lambda r: r["days_left"])
    agenda.sort(key=lambda r: r["days_until"])

    return {
        "generated_at": today.isoformat(),
        "act_now": {
            "gate_blocked": blocked,
            "offers_pending": offer_status.get("Pending", 0),
            "certs_expiring_30d": certs_expiring_30,
            "referencing_pending": referencing_pending,
            "movein_ready": by_stage[7],
            "overdue_diary": overdue,
        },
        "pipeline": {
            "by_stage": [
                {"order": i, "name": _STAGE_NAMES.get(i), "count": by_stage[i]}
                for i in range(1, 10)
            ],
            "split": {"pre_tenancy": pre_tenancy, "active": active, "ending": ending},
            "total": len(props),
            "stalled": stalled[:LIST_CAP],
        },
        "compliance": {
            "breakdown": comp,
            "expiry_runway": expiry_runway[:LIST_CAP],
            "epc_fg": epc_fg,
            "hmo_unconfirmed": hmo_unconfirmed,
        },
        "upcoming": {
            "diary_agenda": agenda[:LIST_CAP],
            "overdue_count": overdue,
        },
        "portfolio": {
            "active_tenancies": active,
            "rent_roll_annual": round(rent_roll_annual, 2),
            "rent_roll_monthly": round(rent_roll_annual / 12.0, 2),
            "tenancy_type_split": type_split,
            "service_level_split": service_split,
            "offer_conversion": offer_status,
        },
    }


# ---------------------------------------------------------------------------
# Result cache. The whole computed dashboard is cached for a short window so
# rapid navigation back to the home page doesn't re-aggregate (the underlying
# table reads are cached too, but this also skips the in-memory crunch). The
# client-cache TTLs already bound staleness; this just caps it independently.
# ?fresh=1 bypasses (e.g. a manual "refresh" button).
# ---------------------------------------------------------------------------
_DASH_TTL = 30.0
_dash_lock = threading.Lock()
_dash_cache: dict[str, Any] = {"at": 0.0, "data": None}


@router.get("")
def get_dashboard(
    fresh: bool = Query(False, description="Bypass the cached snapshot"),
    _: Agent = Depends(require_agent),
) -> dict[str, Any]:
    now = time.monotonic()
    if not fresh:
        with _dash_lock:
            data = _dash_cache["data"]
            if data is not None and (now - _dash_cache["at"]) < _DASH_TTL:
                return data
    data = _build_dashboard()
    with _dash_lock:
        _dash_cache["data"] = data
        _dash_cache["at"] = time.monotonic()
    return data
