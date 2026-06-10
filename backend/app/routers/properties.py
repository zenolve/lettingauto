"""Agent-facing CRUD over Airtable properties."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import Agent, require_agent
from app.core.logger import get_logger
from app.db import supabase_client as at

router = APIRouter(prefix="/api/properties", tags=["properties"])
logger = get_logger(__name__)


@router.get("/")
def list_properties(_: Agent = Depends(require_agent)) -> list[dict]:
    rows = at.all_records(at.TableNames.PROPERTIES)
    # Default order: newest first by Airtable createdTime. Airtable returns
    # `createdTime` as an ISO datetime on every record. The dashboard sorts
    # client-side too, but doing it here means the table doesn't flicker on
    # first render.
    rows.sort(key=lambda r: r.get("createdTime") or "", reverse=True)
    return [_to_summary(r) for r in rows]


@router.get("/{property_id}/latest-review")
def get_latest_review(property_id: str, _: Agent = Depends(require_agent)) -> dict[str, Any]:
    """Return the most recent non-dismissed Gate_Log row for this property
    that carries warnings or actions. Used by the property page to render the
    compliance-review panel."""
    # Filter: linked to this property AND has either Gate Warnings or Gate
    # Actions populated AND not dismissed. Airtable doesn't expose the link's
    # record_id directly in filterByFormula, so we walk the property's
    # Gate_Log link instead â€” cheaper and avoids fragile formula tricks.
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    linked_ids: list[str] = prop.get("fields", {}).get("Gate_Log", []) or []
    if not linked_ids:
        return {"review": None}

    candidates: list[dict] = []
    for rid in linked_ids:
        try:
            row = at.get(at.TableNames.GATE_LOG, rid)
        except Exception:
            continue
        f = row.get("fields", {})
        if f.get("Gate Warnings Dismissed"):
            continue
        if not (f.get("Gate Warnings") or f.get("Gate Actions")):
            continue
        candidates.append({"id": row["id"], **f, "_attempted": f.get("Attempted_At") or ""})

    if not candidates:
        return {"review": None}

    candidates.sort(key=lambda r: r["_attempted"], reverse=True)
    latest = candidates[0]

    def _lines(v: Any) -> list[str]:
        if not v:
            return []
        return [s.strip() for s in str(v).split("\n") if s.strip()]

    return {
        "review": {
            "gate_log_id":   latest["id"],
            "warnings":      _lines(latest.get("Gate Warnings")),
            "actions":       _lines(latest.get("Gate Actions")),
            "source":        latest.get("Gate Warnings Source"),
            "updated":       latest.get("Gate Warnings Updated"),
            "attempted_at":  latest.get("Attempted_At"),
            "result":        latest.get("Result"),
        },
    }


@router.get("/{property_id}/all-warnings")
def get_all_warnings(property_id: str, _: Agent = Depends(require_agent)) -> dict[str, Any]:
    """Read-only recap of every warning/action ever raised on this property,
    regardless of dismissal status.

    Powers the WarningsRecap panel mounted under the Stage 7 checklist.
    Stage 7 is the natural endpoint because no Gate_Log warnings are
    generated after it (PG_05/06/07 don't write warnings; PG_04 webhook
    decline events are the only theoretical post-7 source and are rare).

    Sorted newest-first. Each group is one Gate_Log row.
    """
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")

    linked_ids: list[str] = prop.get("fields", {}).get("Gate_Log", []) or []
    if not linked_ids:
        return {"groups": []}

    def _lines(v: Any) -> list[str]:
        if not v:
            return []
        return [s.strip() for s in str(v).split("\n") if s.strip()]

    groups: list[dict[str, Any]] = []
    for rid in linked_ids:
        try:
            row = at.get(at.TableNames.GATE_LOG, rid)
        except Exception:
            continue
        f = row.get("fields", {})
        warnings = _lines(f.get("Gate Warnings"))
        actions = _lines(f.get("Gate Actions"))
        if not (warnings or actions):
            continue
        groups.append({
            "gate_log_id":   row["id"],
            "source":        f.get("Gate Warnings Source") or "â€”",
            "to_stage":      f.get("To_Stage"),
            "attempted_at":  f.get("Attempted_At") or "",
            "updated":       f.get("Gate Warnings Updated"),
            "dismissed":     bool(f.get("Gate Warnings Dismissed")),
            "warnings":      warnings,
            "actions":       actions,
        })

    groups.sort(key=lambda g: g["attempted_at"], reverse=True)
    return {"groups": groups}


@router.post("/{property_id}/latest-review/{gate_log_id}/dismiss", status_code=status.HTTP_200_OK)
def dismiss_review(
    property_id: str,
    gate_log_id: str,
    agent: Agent = Depends(require_agent),
) -> dict[str, Any]:
    """Flip ``Gate Warnings Dismissed`` on a specific Gate_Log row. We re-check
    the link to the property to stop a stray id from being dismissed."""
    try:
        row = at.get(at.TableNames.GATE_LOG, gate_log_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gate_Log row not found")
    linked = (row.get("fields", {}).get("Property") or [])
    if property_id not in linked:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Gate_Log row is not linked to this property")
    at.update(at.TableNames.GATE_LOG, gate_log_id, {
        "Gate Warnings Dismissed": True,
        "Resolved_By": agent.email,
        # Resolved_At intentionally only set when a gate failure was actually
        # resolved (not when a warning batch is dismissed). The dismiss flag
        # is the sole field that hides the row from the agent UI.
    })
    return {"dismissed": gate_log_id}


# ---------------------------------------------------------------------------
# POST /reevaluate-gate â€” manual re-check after fixing data
# ---------------------------------------------------------------------------
# Airtable edits (or external integrations) don't trigger our gate logic, so
# the cached Gate Status / Gate Block Reason can lag behind reality. This
# endpoint re-derives the property's current stage from its fields and runs
# evaluate_gate against the next stage with silent=True (no agent emails â€”
# the agent is staring at the page; the response IS the feedback).
@router.post("/{property_id}/reevaluate-gate", status_code=status.HTTP_200_OK)
async def reevaluate_gate(
    property_id: str,
    _: Agent = Depends(require_agent),
) -> dict[str, Any]:
    from app.handlers.pg00_gate import evaluate_gate  # local import â€” keeps load-time graph slim
    from app.routers.forms import _derive_current_stage_for_check  # noqa: PLC0415

    # The whole point of "re-evaluate" is to reflect out-of-band Airtable edits
    # the agent just made, so drop the cached reads for the tables the gate
    # inspects before we re-read them.
    at.invalidate(at.TableNames.PROPERTIES)
    at.invalidate(at.TableNames.TENANTS)

    try:
        at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")

    current = _derive_current_stage_for_check(property_id)
    target = current + 1
    # No gate to evaluate past stage 8 â€” TRANSITIONS stops there. But a stale
    # "Blocked" status can linger on the property from an earlier failed
    # evaluation (e.g. the 6â†’7 gate blocked while the TA was unsigned; the
    # agent then completed signing, so the property now DERIVES to stage 8 but
    # its cached Gate Status / Gate Block Reason still read Blocked). Since the
    # property has cleared every tracked gate, reconcile by clearing that stale
    # block â€” otherwise "Re-evaluate gate" appears to do nothing. (Reported
    # 2026-05-25: gate still showed "TA_LL_Signed not set" after the fields
    # were all set true in Airtable.)
    if target > 8:
        fresh = at.get(at.TableNames.PROPERTIES, property_id).get("fields", {})
        cleared = False
        if fresh.get("Gate Status") == "Blocked":
            at.update(at.TableNames.PROPERTIES, property_id, {
                "Gate Status": "Clear",
                "Gate Block Reason": "",
            })
            cleared = True
        return {
            "property_id": property_id,
            "current_stage": current,
            "target_stage": target,
            "no_op": True,
            "cleared_stale_block": cleared,
            "message": (
                "Property has cleared every tracked gate. "
                + ("Cleared a stale block left over from an earlier evaluation."
                   if cleared else "No further gate to evaluate.")
            ),
        }
    gate = await evaluate_gate(property_id, target_stage=target, silent=True)
    return {
        "property_id": property_id,
        "current_stage": current,
        "target_stage": target,
        "advanced": gate.advanced,
        "failures": gate.failures,
    }


# ---------------------------------------------------------------------------
# PATCH /flags â€” agent toggles for gate-blocking booleans
# ---------------------------------------------------------------------------
# Whitelisted Properties fields the agent can edit directly from the UI. Each
# entry declares the value type and, for ``bool_with_date``, the paired date
# column to auto-stamp on tick and clear on untick. Adding a field here is
# the only thing needed to expose it through the patch endpoint â€” the
# frontend component looks it up via /api/properties/flags-catalog.
# Each entry's `confirm` block (when present) tells the frontend to gate the
# write behind a modal â€” used for the signing flags where bypassing the
# pipeline has audit-trail implications.
_SIGNING_OVERRIDE_CONFIRM = {
    "title": "Manual signing override",
    "body": (
        "You are about to set this signature flag without going through the "
        "DocuSign envelope. Make sure ALL named parties have signed (wet-ink "
        "or via another channel) and that the signed PDF is on file before "
        "continuing. This bypasses the normal audit trail."
    ),
    "confirmLabel": "Yes, mark as signed",
    "tone": "warning",
}

PATCHABLE_FLAGS: dict[str, dict[str, Any]] = {
    # --- Signing overrides (gates: 2â†’3, 3â†’4 for TC; 6â†’7 for TA) ---------
    # Set by the DocuSign Connect webhook on the happy path. Surfaced here
    # for wet-ink offline signing, webhook failures, retroactive migration,
    # and amendment-resigning cases where DocuSign won't re-fire.
    "TC_Signed":                     {"type": "bool", "label": "T&C signed (manual override)",
                                       "confirm": _SIGNING_OVERRIDE_CONFIRM},
    "TA_LL_Signed":                  {"type": "bool", "label": "TA signed by landlord (manual override)",
                                       "confirm": _SIGNING_OVERRIDE_CONFIRM},
    "TA_TT_Signed":                  {"type": "bool", "label": "TA signed by ALL tenants (manual override)",
                                       "confirm": _SIGNING_OVERRIDE_CONFIRM},
    # --- Stage 5 entry (offer-accepted gate) ---
    "HMO_Licence_Confirmed":         {"type": "bool",           "label": "HMO licence confirmed"},
    "Anti_Discrimination_Confirmed": {"type": "bool_with_date", "label": "Anti-discrimination confirmed",
                                       "date_field": "Anti_Discrimination_Confirmed_Date"},
    # --- Stage 7 entry (TA-signed gate) ---
    "TDS Cert On File":              {"type": "bool",           "label": "TDS certificate on file"},
    "Deposit Registered":            {"type": "bool_with_date", "label": "Deposit registered with TDS",
                                       "date_field": "Deposit Registration Date"},
    # --- Stage 8 entry (pre-move-in gate) ---
    "funds_cleared":                 {"type": "bool",           "label": "Funds cleared"},
    "Works_Signed_Off":              {"type": "bool",           "label": "Works signed off"},
    # Per-doc served flags â€” usually flipped by the tenant-pack handler, but
    # exposed here for cases where the doc was served outside the system.
    "How_To_Rent_Served":            {"type": "bool",           "label": "How To Rent served"},
    "Gas_Cert_Served":               {"type": "bool",           "label": "Gas certificate served"},
    "EPC_Served":                    {"type": "bool",           "label": "EPC served"},
    "EICR_Served":                   {"type": "bool",           "label": "EICR served"},
    "TDS_Info_Served":               {"type": "bool",           "label": "TDS prescribed info served"},
    "RRA_Sheet_Served":              {"type": "bool",           "label": "RRA sheet served (APT only)"},
    # --- Text fields (no gate impact, but no other UI today) ---
    "Inventory_Clerk":               {"type": "text",           "label": "Inventory clerk"},
    "Westminster_Licence_Number":    {"type": "text",           "label": "Westminster licence number"},
}


@router.get("/flags-catalog")
def flags_catalog(_: Agent = Depends(require_agent)) -> dict[str, Any]:
    """Tell the frontend which flags exist + their metadata.

    Keeps the registry in one place â€” the React component can render any
    subset of these without each call site duplicating the labels."""
    return {
        "fields": [
            {"name": name, **meta}
            for name, meta in PATCHABLE_FLAGS.items()
        ],
    }


@router.patch("/{property_id}/flags")
def patch_flags(
    property_id: str,
    body: dict[str, Any],
    _: Agent = Depends(require_agent),
) -> dict[str, Any]:
    """Apply a partial update of allow-listed Properties fields.

    Body shape: ``{"funds_cleared": true, "Inventory_Clerk": "Acme"}``.
    For each key:
      - bool fields: coerce to True/False
      - bool_with_date: also writes today (on tick) or null (on untick) to the
        paired date column declared in ``PATCHABLE_FLAGS``
      - text: pass-through; an empty string clears the field

    Unknown keys â†’ 400. We deliberately don't re-evaluate the gate here so
    toggling a flag doesn't fire stage-advance emails â€” agents trigger that
    flow explicitly via the existing form submissions.
    """
    if not isinstance(body, dict) or not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "body must be a non-empty object")

    unknown = [k for k in body if k not in PATCHABLE_FLAGS]
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Field(s) not patchable: {', '.join(unknown)}",
        )

    from datetime import date as _date  # local â€” keep import-time graph slim
    today = _date.today().isoformat()

    payload: dict[str, Any] = {}
    for k, raw in body.items():
        meta = PATCHABLE_FLAGS[k]
        t = meta["type"]
        if t == "bool":
            payload[k] = bool(raw)
        elif t == "bool_with_date":
            checked = bool(raw)
            payload[k] = checked
            # auto-stamp / clear the paired date column
            payload[meta["date_field"]] = today if checked else None
        elif t == "text":
            payload[k] = "" if raw is None else str(raw)
        else:  # pragma: no cover â€” defensive, registry is internal
            raise HTTPException(500, f"Unknown field type {t!r} for {k}")

    try:
        at.update(at.TableNames.PROPERTIES, property_id, payload)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Airtable rejected the update: {e}")

    # Re-read so the client sees Airtable's normalised values (e.g. a
    # boolean field returns False as the literal key being absent).
    fresh = at.get(at.TableNames.PROPERTIES, property_id).get("fields", {})
    return {
        "property_id": property_id,
        "updated": {k: fresh.get(k) for k in payload},
    }


@router.delete("/{property_id}", status_code=status.HTTP_200_OK)
def delete_property(property_id: str, _: Agent = Depends(require_agent)) -> dict[str, Any]:
    """Permanently delete a property and everything that belongs to it.

    Cascade: all linked Tenants (accepted + every offer's applicants), Offers,
    Diary entries, Compliance rows, Financials, Gate_Log, Submissions and
    Sent_Documents, plus the uploaded-files directory. A linked Landlord is
    deleted only when this was their **sole** property â€” otherwise it's left in
    place (Airtable clears the link automatically). Shared catalog links
    (Tenancy Checklist) are not deleted, only unlinked.

    Irreversible. The frontend gates this behind a danger confirmation modal.
    """
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id, fresh=True)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    f = prop.get("fields", {})
    deleted: dict[str, int] = {}

    # Tenants: union of the accepted link + every offer's applicants.
    tenant_ids: set[str] = set(f.get("Tenant") or [])
    offer_ids: list[str] = list(f.get("Offers") or [])
    for oid in offer_ids:
        try:
            of = at.get(at.TableNames.OFFERS, oid).get("fields", {})
            tenant_ids.update(of.get("Tenants") or [])
        except Exception:
            pass

    cascades: list[tuple[str, list[str]]] = [
        (at.TableNames.TENANTS, list(tenant_ids)),
        (at.TableNames.OFFERS, offer_ids),
        (at.TableNames.DIARY, list(f.get("Diary") or [])),
        (at.TableNames.COMPLIANCE, list(f.get("Compliance") or [])),
        (at.TableNames.FINANCIALS, list(f.get("Financials") or [])),
        (at.TableNames.GATE_LOG, list(f.get("Gate_Log") or [])),
        (at.TableNames.SUBMISSIONS, list(f.get("Submissions") or [])),
        (at.TableNames.SENT_DOCUMENTS, list(f.get("Sent_Documents") or [])),
    ]
    for tbl, ids in cascades:
        n = 0
        for rid in ids:
            try:
                at.delete(tbl, rid)
                n += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("delete.cascade_failed table=%s id=%s err=%s", tbl, rid, e)
        deleted[tbl] = n

    # Landlords: delete only if this property is their only one. Read fresh â€”
    # a cached landlord record could show a stale Properties list (e.g. a
    # property deleted seconds ago), and getting this wrong on a destructive
    # op would either orphan a landlord or wrongly delete one with other
    # properties.
    ll_deleted = 0
    for lid in f.get("Landlords") or []:
        try:
            ll = at.get(at.TableNames.LANDLORDS, lid, fresh=True).get("fields", {})
            others = [p for p in (ll.get("Properties") or []) if p != property_id]
            if not others:
                at.delete(at.TableNames.LANDLORDS, lid)
                ll_deleted += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("delete.landlord_failed id=%s err=%s", lid, e)
    deleted["landlords"] = ll_deleted

    # Uploaded files + the per-property doc queue.
    try:
        import shutil  # noqa: PLC0415
        from app.routers.uploads import UPLOADS_ROOT  # noqa: PLC0415
        shutil.rmtree(UPLOADS_ROOT / property_id, ignore_errors=True)
        q = UPLOADS_ROOT / "_queues" / f"{property_id}.json"
        if q.exists():
            q.unlink()
    except Exception as e:  # noqa: BLE001
        logger.warning("delete.uploads_failed property=%s err=%s", property_id, e)

    # Finally the property itself. Deleting it changes the reverse-link list on
    # any surviving landlord, so drop the Landlords cache too (the property's
    # own delete only invalidates the Properties table).
    at.delete(at.TableNames.PROPERTIES, property_id)
    at.invalidate(at.TableNames.LANDLORDS)
    deleted["property"] = 1
    logger.info("property.deleted id=%s cascade=%s", property_id, deleted)
    return {"deleted_property": property_id, "deleted": deleted}


@router.get("/{property_id}")
def get_property(property_id: str, _: Agent = Depends(require_agent)) -> dict[str, Any]:
    prop = at.get(at.TableNames.PROPERTIES, property_id)
    fields = prop.get("fields", {})

    landlords = []
    for lid in fields.get("Landlords", []) or []:
        try:
            landlords.append({"id": lid, **at.get(at.TableNames.LANDLORDS, lid).get("fields", {})})
        except Exception:
            pass

    tenant = None
    if fields.get("Tenant"):
        try:
            tid = fields["Tenant"][0]
            tenant = {"id": tid, **at.get(at.TableNames.TENANTS, tid).get("fields", {})}
        except Exception:
            tenant = None

    return {
        "id": prop["id"],
        "fields": fields,
        "landlords": landlords,
        "tenant": tenant,
    }


_STAGE_NAMES = {
    1: "Take-on", 2: "Compliance", 3: "Marketing", 4: "Offer",
    5: "Referencing", 6: "TA Signing", 7: "Pre Move-in",
    8: "Live Tenancy", 9: "End of Tenancy",
}


def _derive_stage_order_from_fields(f: dict) -> int:
    """Stage derivation from a Property fields dict.

    Keep in sync with the frontend [stages.ts:deriveCurrentStage] and the
    backend [forms.py:_derive_current_stage_for_check] â€” same priorities,
    most-advanced-state first. Inlined here to keep the dashboard list
    endpoint a single Airtable read per page load.
    """
    if f.get("TA_LL_Signed") and f.get("TA_TT_Signed"):
        return 8
    tenant_linked = bool(f.get("Tenant"))
    if tenant_linked and (f.get("TA_LL_Signed") or f.get("TA_TT_Signed")):
        return 7
    if tenant_linked and f.get("LL_Offer_Accepted"):
        return 6
    if tenant_linked:
        return 5
    if f.get("TC_Signed"):
        return 4
    cert_keys = ("Gas_Cert_Status", "EPC_Status", "EICR_Status")
    if all(f.get(k) in ("On File", "Palace Gate Arranging") for k in cert_keys):
        return 3
    if bool(f.get("Landlords")) and any(f.get(k) for k in cert_keys):
        return 2
    return 1


def _to_summary(record: dict) -> dict:
    f = record.get("fields", {})
    stage_order = _derive_stage_order_from_fields(f)
    return {
        "id": record["id"],
        "address": f.get("Address"),
        "post_code": f.get("post_code") or f.get("Post Code"),
        "tenancy_type": f.get("Tenancy Type"),
        "gate_status": f.get("Gate Status"),
        "gate_block_reason": f.get("Gate Block Reason"),
        "stage_changed_at": f.get("Stage changed at"),
        "service_level": f.get("Service Level"),
        "stage_order": stage_order,
        "stage_name": _STAGE_NAMES.get(stage_order),
        "tc_signed": f.get("TC_Signed"),
        "ta_ll_signed": f.get("TA_LL_Signed"),
        "ta_tt_signed": f.get("TA_TT_Signed"),
        "created_at": record.get("createdTime"),
    }


@router.get("/{property_id}/diary")
def property_diary(property_id: str, _: Agent = Depends(require_agent)) -> dict:
    """Return all diary entries linked to this property, sorted by Alert_Date.

    Used by the Stage 8 (Live Tenancy) widget to render rent-review, cert
    renewals, NRL, RTR follow-up etc. as a real list rather than a placeholder.
    """
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id)
    except Exception as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Property not found: {e}")
    diary_ids = prop.get("fields", {}).get("Diary") or []
    rows: list[dict] = []
    for did in diary_ids:
        try:
            d = at.get(at.TableNames.DIARY, did)
            f = d.get("fields", {})
            rows.append({
                "id": d["id"],
                "type": f.get("Diary_Type"),
                "alert_date": f.get("Alert_Date"),
                "diary_date": f.get("Diary Date"),
                "message": f.get("Alert_Message"),
                "assigned_to": f.get("Assigned_To"),
                "fired": bool(f.get("Fired")),
                "fired_date": f.get("Fired_Date"),
            })
        except Exception:
            pass
    rows.sort(key=lambda r: r.get("alert_date") or "9999-12-31")
    return {"property_id": property_id, "entries": rows}
