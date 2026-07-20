"""PG_00 — Gate evaluator (spec §3.1).

Not an HTTP endpoint: a reusable function called by other handlers after their
work is complete. Evaluates the conditions for the *next* stage and either
advances the property or marks it blocked with a reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from app.core.email_client import send_agent_summary
from app.core.logger import get_logger
from app.db import supabase_client as at
from app.services.derivations import parse_iso_date

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------
def find_stage_by_order(order: int) -> dict | None:
    return at.find_first(at.TableNames.STAGES, at.eq("Order", order))


def find_stage_agent_email(order: int) -> str | None:
    stage = find_stage_by_order(order)
    if not stage:
        return None
    val = stage.get("fields", {}).get("Stage agent")
    if not val:
        return None
    # Live Airtable has "Stage agent" as multipleCollaborators → list of
    # {id, email, name} dicts. Tolerate plain string too in case the schema
    # is ever changed back to an email field.
    if isinstance(val, list):
        first = val[0] if val else None
        if isinstance(first, dict):
            return first.get("email")
        return first if isinstance(first, str) else None
    if isinstance(val, dict):
        return val.get("email")
    return val if isinstance(val, str) else None


# ---------------------------------------------------------------------------
# Gate condition definitions
# ---------------------------------------------------------------------------
@dataclass
class GateResult:
    advanced: bool
    target_stage: int
    failures: list[str]

    def to_dict(self) -> dict:
        return {"advanced": self.advanced, "target_stage": self.target_stage,
                "failures": self.failures}


# Each condition takes the Properties field-dict and returns "" if it passes,
# or a human-readable reason if it fails.
Condition = Callable[[dict], str]


def _ok() -> str:
    return ""


def _cert_status_acceptable(field: dict, key: str) -> str:
    v = field.get(key)
    if v in ("On File", "Agency Arranging"):
        return ""
    return f"{key} = {v or 'missing'}"


def _epc_not_fg(field: dict) -> str:
    if field.get("EPC_Status") == "On File":
        rating = (field.get("EPC Rating") or "").upper()
        if rating in ("F", "G"):
            return f"EPC rating is {rating} (cannot legally let)"
    return ""


def _date_not_expired(field: dict, key: str) -> str:
    val = field.get(key)
    d = parse_iso_date(val) if isinstance(val, str) else val
    if d and isinstance(d, date) and d < date.today():
        return f"{key} expired ({d.isoformat()})"
    return ""


def _bool_true(field: dict, key: str) -> str:
    return "" if field.get(key) else f"{key} not set"


def _has_linked(field: dict, key: str) -> str:
    val = field.get(key) or []
    return "" if val else f"No {key} linked"


def _all_tenants_have(field: dict, key: str) -> str:
    """Pass when every linked Tenant on this property has ``key`` truthy.

    Used for Stage 5→6: Referencing_Recorded and Landlord_Approval_Received
    are per-tenant checkboxes on the Tenants table (not Properties).
    """
    tenant_ids = field.get("Tenant") or []
    if not tenant_ids:
        return "No tenant linked"
    missing: list[str] = []
    for tid in tenant_ids:
        try:
            tf = at.get(at.TableNames.TENANTS, tid).get("fields", {})
        except Exception:
            missing.append(tid)
            continue
        if not tf.get(key):
            missing.append(tf.get("Name") or tid)
    if missing:
        return f"{key} missing for: {', '.join(missing)}"
    return ""


# Map of stage transitions to a list of (label, fn) pairs.
TRANSITIONS: dict[int, list[tuple[str, Condition]]] = {
    2: [  # 1 → 2: take-on complete
        ("Landlord linked", lambda f: _has_linked(f, "Landlords")),
    ],
    3: [  # 2 → 3: compliance complete
        ("Gas cert status", lambda f: _cert_status_acceptable(f, "Gas_Cert_Status")),
        ("EPC status", lambda f: _cert_status_acceptable(f, "EPC_Status")),
        ("EICR status", lambda f: _cert_status_acceptable(f, "EICR_Status")),
        ("EPC not F/G", _epc_not_fg),
        ("Gas cert not expired",
         lambda f: _date_not_expired(f, "Gas Certificates Expiry") if f.get("Gas_Cert_Status") == "On File" else _ok()),
        ("EICR not expired",
         lambda f: _date_not_expired(f, "EICR Expiry") if f.get("EICR_Status") == "On File" else _ok()),
        ("T&C signed", lambda f: _bool_true(f, "TC_Signed")),
    ],
    4: [  # 3 → 4: marketing complete
        ("T&C signed", lambda f: _bool_true(f, "TC_Signed")),
    ],
    5: [  # 4 → 5: offer accepted
        ("Landlord offer accepted", lambda f: _bool_true(f, "LL_Offer_Accepted")),
        ("Anti-discrimination confirmed (APT only)",
         lambda f: _bool_true(f, "Anti_Discrimination_Confirmed") if f.get("Tenancy Type") == "APT" else _ok()),
        ("HMO licence confirmed",
         lambda f: _bool_true(f, "HMO_Licence_Confirmed") if f.get("HMO_Flag") else _ok()),
    ],
    6: [  # 5 → 6: referencing complete.
        # Per-tenant: every named tenant has a recorded referencing outcome.
        ("Referencing outcome recorded", lambda f: _all_tenants_have(f, "Referencing_Recorded")),
        # Property-level: landlord has accepted the offer (= LL_Offer_Accepted).
        # We deliberately re-use the existing checkbox rather than introducing
        # a duplicate Landlord_Approval_Received field — they mean the same
        # thing operationally (the landlord has approved the tenancy).
        ("Landlord approval received",   lambda f: _bool_true(f, "LL_Offer_Accepted")),
    ],
    7: [  # 6 → 7: TA signed
        ("TA signed by landlord", lambda f: _bool_true(f, "TA_LL_Signed")),
        ("TA signed by tenant", lambda f: _bool_true(f, "TA_TT_Signed")),
        ("TDS cert on file", lambda f: _bool_true(f, "TDS Cert On File")),
        ("Deposit registered", lambda f: _bool_true(f, "Deposit Registered")),
    ],
    8: [  # 7 → 8: pre move-in complete
        ("Funds cleared", lambda f: _bool_true(f, "funds_cleared")),
        ("How To Rent served", lambda f: _bool_true(f, "How_To_Rent_Served")),
        ("Gas cert served", lambda f: _bool_true(f, "Gas_Cert_Served")),
        ("EPC served", lambda f: _bool_true(f, "EPC_Served")),
        ("EICR served", lambda f: _bool_true(f, "EICR_Served")),
        ("TDS info served", lambda f: _bool_true(f, "TDS_Info_Served")),
        ("RRA sheet served (APT only)",
         lambda f: _bool_true(f, "RRA_Sheet_Served") if f.get("Tenancy Type") == "APT" else _ok()),
        ("Works signed off", lambda f: _bool_true(f, "Works_Signed_Off")),
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def evaluate_gate(
    property_id: str,
    target_stage: int,
    *,
    warnings: list[str] | None = None,
    actions: list[str] | None = None,
    source: str | None = None,
    silent: bool = False,
) -> GateResult:
    """Evaluate the gate for the given property record and target stage.

    On success: advances `Stage` to the target stage record, sets Gate Status
    to "Clear", logs a Gate Log entry, and emails the agent.
    On failure: sets Gate Status to "Blocked", writes Gate Block Reason,
    and emails the agent with the failure list.

    `warnings`, `actions`, `source` (optional): if a caller has just run a
    compliance/review pass, pass the resulting non-blocking warnings/actions
    through so they land on the same Gate_Log row. The agent UI reads the
    latest Gate_Log row and surfaces these to the user.

    `silent` (default False): when True, skip the agent-summary email. The
    Gate_Log row is still written for audit. Used by the manual
    "Re-evaluate gate" button on the property page, so re-running the check
    after fixing data doesn't spam the agent's inbox.
    """
    prop = at.get(at.TableNames.PROPERTIES, property_id)
    fields = prop.get("fields", {})

    conditions = TRANSITIONS.get(target_stage, [])
    failures: list[str] = []
    for label, fn in conditions:
        reason = fn(fields)
        if reason:
            failures.append(f"{label}: {reason}")

    target_record = find_stage_by_order(target_stage)
    target_stage_id = target_record["id"] if target_record else None

    if failures:
        block_reason = "; ".join(failures)
        update_fields: dict = {
            "Gate Status": "Blocked",
            "Gate Block Reason": block_reason,
        }
        at.update(at.TableNames.PROPERTIES, property_id, update_fields)
        await _log_gate(
            property_id, target_stage, passed=False, reasons=failures,
            warnings=warnings, actions=actions, source=source,
        )
        if not silent:
            agent_email = find_stage_agent_email(target_stage)
            await send_agent_summary(
                agent_email or "",
                subject=f"Gate blocked — Stage {target_stage} — {fields.get('Address', '')}",
                template="E12_gate_blocked.html",
                context={
                    "property_address": fields.get("Address"),
                    "target_stage": target_stage,
                    "failures": failures,
                    "warnings": failures,
                },
            )
        logger.info("gate.blocked property=%s target=%s failures=%s silent=%s",
                    property_id, target_stage, failures, silent)
        return GateResult(advanced=False, target_stage=target_stage, failures=failures)

    # Success — advance
    update_fields = {
        "Gate Status": "Clear",
        "Gate Block Reason": "",
        "Stage changed at": date.today().isoformat(),
    }
    if target_stage_id:
        update_fields["Stage"] = [target_stage_id]
    at.update(at.TableNames.PROPERTIES, property_id, update_fields)
    await _log_gate(
        property_id, target_stage, passed=True, reasons=[],
        warnings=warnings, actions=actions, source=source,
    )
    if not silent:
        agent_email = find_stage_agent_email(target_stage)
        await send_agent_summary(
            agent_email or "",
            subject=f"Stage {target_stage} reached — {fields.get('Address', '')}",
            template="E13_stage_advanced.html",
            context={
                "property_address": fields.get("Address"),
                "target_stage": target_stage,
                "flags": [],
            },
        )
    logger.info("gate.advanced property=%s target=%s silent=%s", property_id, target_stage, silent)
    return GateResult(advanced=True, target_stage=target_stage, failures=[])


async def _log_gate(
    property_id: str,
    target_stage: int,
    *,
    passed: bool,
    reasons: list[str],
    warnings: list[str] | None = None,
    actions: list[str] | None = None,
    source: str | None = None,
) -> None:
    """Write an audit row to the Gate_Log table.

    Field names match the live Airtable schema (Result singleSelect:
    Passed/Blocked; Attempted_At dateTime; From_Stage/To_Stage as strings).

    Non-blocking compliance findings — `warnings`, `actions`, `source` —
    are written to the Gate Warnings / Gate Actions / Gate Warnings Source
    columns when supplied so the agent UI can render them on the property
    page. ``Gate Warnings Updated`` carries today's date so dismissals from
    older runs don't accidentally hide a fresh batch.
    """
    fields: dict = {
        "Property": [property_id],
        "Attempted_At": datetime.now(timezone.utc).isoformat(),
        "From_Stage": str(target_stage - 1),
        "To_Stage": str(target_stage),
        "Result": "Passed" if passed else "Blocked",
        "Block_Reason": "\n".join(reasons) if reasons else "",
    }
    if warnings:
        fields["Gate Warnings"] = "\n".join(warnings)
    if actions:
        fields["Gate Actions"] = "\n".join(actions)
    if warnings or actions:
        # Stamping these only when there's content keeps "no warnings to show"
        # rows out of the agent's review queue without an explicit IS_BLANK
        # filter on the UI side.
        fields["Gate Warnings Updated"] = date.today().isoformat()
        if source:
            fields["Gate Warnings Source"] = source
    try:
        at.create(at.TableNames.GATE_LOG, fields)
    except Exception as e:  # noqa: BLE001
        logger.warning("gate_log.write_failed err=%s", e)
