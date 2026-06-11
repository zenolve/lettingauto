"""Internal form submission endpoints â€” these REPLACE the Tally forms.

The React frontend POSTs to these. They dispatch into the same handlers that
the legacy Tally webhooks use, so business logic stays in one place.

Public form routes (`POST /api/forms/landlord-*`) require a form token that
encodes the property + form + landlord email so we can match the submission
back to the right Airtable record.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import Agent, decode_form_token, require_agent
from app.handlers.pg01_takeon import handle_takeon
from app.handlers.pg02_admin import handle_admin
from app.handlers.pg02b_verification import handle_verification
from app.handlers.pg03_offer import handle_offer
from app.handlers.pg05_tenant_pack import handle_tenant_pack
from app.handlers.pg06_scheduler import run_scheduler
from app.handlers.pg07_rra_batch import handle_rra_batch
from app.models.common import (
    LandlordAdminInput,
    LandlordVerificationInput,
    OfferInput,
    PropertyTakeonInput,
)

router = APIRouter(prefix="/api/forms", tags=["forms"])


# ---------------------------------------------------------------------------
# Agent-protected
# ---------------------------------------------------------------------------
@router.post("/property-takeon", status_code=status.HTTP_201_CREATED)
async def submit_property_takeon(
    payload: PropertyTakeonInput,
    _: Agent = Depends(require_agent),
) -> dict:
    from app.services.billing import BillingError  # noqa: PLC0415
    try:
        return await handle_takeon(payload)
    except BillingError as e:
        # The £50 new-tenancy fee could not be charged — surface as Payment
        # Required with a machine-readable code so the UI can route the agent
        # to Settings → Billing.
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail={"code": e.code, "message": str(e)},
        )


def _derive_current_stage_for_check(property_id: str) -> int:
    """Lightweight stage derivation for the stage-gate guard.

    Mirrors `app.routers.properties._derive_current_stage` but inline to avoid
    a circular import. Kept in sync by hand â€” see also frontend/src/lib/stages.ts.
    """
    from app.db import supabase_client as at  # local import â€” avoid load-time cycles
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    f = prop.get("fields", {})
    tenant = bool(f.get("Tenant"))
    if f.get("TA_LL_Signed") and f.get("TA_TT_Signed"):
        return 8
    if tenant and (f.get("TA_LL_Signed") or f.get("TA_TT_Signed")):
        return 7
    if tenant and f.get("LL_Offer_Accepted"):
        return 6
    if tenant:
        return 5
    if f.get("TC_Signed"):
        return 4
    certs_ok = all(f.get(k) in ("On File", "Agency Arranging") for k in ("Gas_Cert_Status", "EPC_Status", "EICR_Status"))
    if certs_ok:
        return 3
    if bool(f.get("Landlords")) and any(f.get(k) for k in ("Gas_Cert_Status", "EPC_Status", "EICR_Status")):
        return 2
    return 1


def _require_stage(property_id: str, required: int, action: str) -> None:
    """Raise 409 Conflict if the property hasn't reached `required` yet."""
    current = _derive_current_stage_for_check(property_id)
    if current < required:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Property is at stage {current}; '{action}' requires stage {required}. "
            f"Resolve the earlier stages first.",
        )


def _require_not_gate_blocked(property_id: str, action: str) -> None:
    """Raise 409 if the property's cached Gate Status is Blocked.

    Reads the cached value (not a fresh re-evaluation) â€” agents already have
    the "Re-evaluate gate" button on the property page for that. If the
    cached state is stale, the agent can clear it via the UI before retry.
    """
    from app.db import supabase_client as at  # local import â€” avoid cycles
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    f = prop.get("fields", {})
    if f.get("Gate Status") == "Blocked":
        reason = (f.get("Gate Block Reason") or "").strip() or "(no reason recorded)"
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Gate is blocked â€” '{action}' cannot proceed. Block reason: {reason}. "
            f"Resolve the blocker (or re-evaluate the gate if data has been fixed) and try again.",
        )


def _require_checklist_complete(property_id: str, action: str) -> None:
    """Raise 409 unless every Tenancy Checklist catalog item is ticked.

    The catalog is small and stable, so a per-call fetch is fine. The check
    is "every item in the catalog is linked into Properties.Tenancy
    Checklist". applies_to-based filtering isn't wired yet (see
    [checklist.py] roadmap note), so today every item applies.
    """
    from app.db import supabase_client as at  # local import â€” avoid cycles
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    try:
        catalog = at.all_records(at.TableNames.CHECKLIST)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Failed to read checklist catalog: {e}")
    ticked = set(prop.get("fields", {}).get("Tenancy Checklist") or [])
    missing = [r for r in catalog if r["id"] not in ticked]
    if missing:
        names = [r.get("fields", {}).get("Name") or "(unnamed)" for r in missing]
        preview = ", ".join(names[:5])
        more = f" (and {len(names) - 5} more)" if len(names) > 5 else ""
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Tenancy checklist incomplete â€” '{action}' requires every item ticked. "
            f"Outstanding: {preview}{more}.",
        )


@router.post("/offer/{property_id}", status_code=status.HTTP_201_CREATED)
async def submit_offer(
    property_id: str,
    payload: OfferInput,
    _: Agent = Depends(require_agent),
) -> dict:
    _require_stage(property_id, required=4, action="Record offer")
    return await handle_offer(property_id, payload)


@router.post("/tenant-pack/{property_id}")
async def submit_tenant_pack(
    property_id: str,
    _: Agent = Depends(require_agent),
) -> dict:
    action = "Send tenant pack"
    _require_stage(property_id, required=7, action=action)
    _require_not_gate_blocked(property_id, action=action)
    _require_checklist_complete(property_id, action=action)
    return await handle_tenant_pack(property_id)


@router.post("/scheduler/run")
async def submit_scheduler_run(
    token: str = Query(...),
    _: Agent | None = None,
) -> dict:
    # Cron-callable: protected by a shared secret rather than agent JWT.
    from app.config import settings
    if token != settings.scheduler_internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid scheduler token")
    return await run_scheduler()


@router.post("/rra-batch")
async def submit_rra_batch(_: Agent = Depends(require_agent)) -> dict:
    return await handle_rra_batch()


# ---------------------------------------------------------------------------
# Public â€” token-protected
# ---------------------------------------------------------------------------
@router.post("/landlord-admin", status_code=status.HTTP_201_CREATED)
async def submit_landlord_admin(
    payload: LandlordAdminInput,
    token: str = Query(...),
) -> dict:
    tok = decode_form_token(token, expected_form="landlord_admin")
    # Scope the request to the agency stamped into the form token so every
    # row this public submission writes lands in (and reads from) the right
    # agency's data.
    from app.db import supabase_client as at  # noqa: PLC0415
    scope = at.set_agency_scope(tok.agency_id)
    try:
        return await handle_admin(tok.property_id, payload)
    finally:
        at.reset_agency_scope(scope)


@router.post("/landlord-verification", status_code=status.HTTP_201_CREATED)
async def submit_landlord_verification(
    payload: LandlordVerificationInput,
    token: str = Query(...),
) -> dict:
    tok = decode_form_token(token, expected_form="landlord_verification")
    from app.db import supabase_client as at  # noqa: PLC0415
    scope = at.set_agency_scope(tok.agency_id)
    try:
        return await handle_verification(tok.property_id, tok.email, payload)
    finally:
        at.reset_agency_scope(scope)
