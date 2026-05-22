"""Agent-facing CRUD over Airtable properties."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import Agent, require_agent
from app.db import airtable_client as at

router = APIRouter(prefix="/api/properties", tags=["properties"])


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
    # Gate_Log link instead — cheaper and avoids fragile formula tricks.
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


def _to_summary(record: dict) -> dict:
    f = record.get("fields", {})
    return {
        "id": record["id"],
        "address": f.get("Address"),
        "post_code": f.get("post_code") or f.get("Post Code"),
        "tenancy_type": f.get("Tenancy Type"),
        "gate_status": f.get("Gate Status"),
        "gate_block_reason": f.get("Gate Block Reason"),
        "stage_changed_at": f.get("Stage changed at"),
        "service_level": f.get("Service Level"),
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
