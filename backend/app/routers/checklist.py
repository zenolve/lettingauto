"""Tenancy checklist â€” Stage 7 (Pre Move-in) widget backing.

Two surfaces:

* ``GET  /api/checklist/catalog`` returns every row in the Airtable
  ``Tenancy Checklist`` table. The catalog rarely changes, so the frontend
  caches it in localStorage and exposes a refresh button rather than
  re-fetching on every page load.

* ``GET  /api/properties/{id}/checklist``        â€” items currently ticked
* ``POST /api/properties/{id}/checklist/{item}`` â€” tick (link the item)
* ``DELETE /api/properties/{id}/checklist/{item}`` â€” untick (unlink)

Ticking writes the catalog row id into ``Properties.Checklist`` (the
multipleRecordLinks field â€” distinct from ``Properties.Tenancy Checklist``,
which is unused). Unticking removes it. We never duplicate catalog rows per
property â€” properties just reference the shared catalog items by link.

(Airtable maintains the reverse link automatically: a tick also makes the
catalog row's ``Properties`` field show this property. The other reverse
field ``Tenancy Checklist.Property`` stays empty because we don't write to
``Properties.Tenancy Checklist``.)

(Future: filter the catalog by ``applies_to`` matching the property's
Tenancy Type / Service Level / Property Type, and pre-populate the
property's checklist on creation. Today neither is wired â€” see the agent's
brief on 2026-05-16.)
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import Agent, require_agent
from app.core.logger import get_logger
from app.db import supabase_client as at

router = APIRouter(tags=["checklist"])
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Catalog â€” every row in the Tenancy Checklist table.
# ---------------------------------------------------------------------------
@router.get("/api/checklist/catalog")
def checklist_catalog(_: Agent = Depends(require_agent)) -> dict:
    """Return every checklist item the agent can pick from.

    Sorted by Priority (Critical â†’ Low) then Name so the most-important items
    surface first when the agent expands the panel.
    """
    try:
        rows = at.all_records(at.TableNames.CHECKLIST)
    except Exception as e:
        raise HTTPException(500, f"Failed to load checklist: {e}")

    priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

    items: list[dict[str, Any]] = []
    for r in rows:
        f = r.get("fields", {})
        items.append({
            "id": r["id"],
            "name": f.get("Name") or "(unnamed)",
            "priority": f.get("Priority"),
            "applies_to": f.get("applies_to") or [],
            "is_template": bool(f.get("Is_Template")),
            "is_gate_item": bool(f.get("is_gate_item")),
            "status": f.get("Status"),
        })
    items.sort(key=lambda it: (priority_order.get(it["priority"] or "", 99), it["name"].lower()))
    return {"items": items, "count": len(items)}


# ---------------------------------------------------------------------------
# Per-property checklist (the linked items on Properties.Checklist).
# ---------------------------------------------------------------------------
def _load_property(property_id: str) -> dict:
    try:
        return at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")


def _current_ids(prop: dict) -> list[str]:
    return list(prop.get("fields", {}).get("Tenancy Checklist") or [])


@router.get("/api/properties/{property_id}/checklist")
def get_property_checklist(
    property_id: str,
    _: Agent = Depends(require_agent),
) -> dict:
    """Return the linked record IDs currently on this property's checklist."""
    prop = _load_property(property_id)
    return {"property_id": property_id, "ticked": _current_ids(prop)}


@router.post("/api/properties/{property_id}/checklist/{item_id}", status_code=status.HTTP_201_CREATED)
def tick_checklist_item(
    property_id: str,
    item_id: str,
    _: Agent = Depends(require_agent),
) -> dict:
    """Add a checklist item to the property's Checklist link.

    Idempotent: ticking an already-ticked item is a no-op.
    """
    prop = _load_property(property_id)
    current = _current_ids(prop)
    if item_id in current:
        return {"property_id": property_id, "ticked": current, "noop": True}
    next_ids = current + [item_id]
    try:
        at.update(at.TableNames.PROPERTIES, property_id, {"Tenancy Checklist": next_ids})
    except Exception as e:
        raise HTTPException(500, f"Tick failed: {e}")
    return {"property_id": property_id, "ticked": next_ids}


@router.delete("/api/properties/{property_id}/checklist/{item_id}")
def untick_checklist_item(
    property_id: str,
    item_id: str,
    _: Agent = Depends(require_agent),
) -> dict:
    """Remove a checklist item from the property's Checklist link."""
    prop = _load_property(property_id)
    current = _current_ids(prop)
    if item_id not in current:
        return {"property_id": property_id, "ticked": current, "noop": True}
    next_ids = [x for x in current if x != item_id]
    try:
        at.update(at.TableNames.PROPERTIES, property_id, {"Tenancy Checklist": next_ids})
    except Exception as e:
        raise HTTPException(500, f"Untick failed: {e}")
    return {"property_id": property_id, "ticked": next_ids}
