"""Certificate renewal -> re-serve the new copy to the sitting tenant.

A renewed gas safety record or EICR must be given to the EXISTING tenant
within **28 days of the inspection** (Gas Safety (Installation and Use) Regs
1998, reg 36; Electrical Safety Standards in the PRS (England) Regs 2020).

The ``*_Served`` flags are set once by the tenant pack and were never reset, so
a mid-tenancy renewal left the record reading "served" against a superseded
copy and no prompt was ever raised. Two entry points feed this module:

* editing an expiry date on the property flags panel (``routers/properties``)
* uploading a replacement certificate with its expiry (``routers/uploads``)

Keying off "the tenant was ALREADY served" is what scopes the behaviour to live
tenancies - a pre-let property has the flag false, so nothing fires.
"""
from __future__ import annotations

from datetime import date as _date
from typing import Any

from app.core.logger import get_logger
from app.db import supabase_client as at

logger = get_logger(__name__)

# expiry field -> (served flag, human doc name, diary type)
RENEWAL_WATCH: dict[str, tuple[str, str, str]] = {
    "Gas Certificates Expiry": ("Gas_Cert_Served", "Gas Safety Certificate", "Gas Cert Re-serve"),
    "EICR Expiry":             ("EICR_Served",     "EICR",                   "EICR Re-serve"),
}

# Upload bucket -> the expiry field that certificate governs. EPC is absent on
# purpose: it lasts 10 years and has no expiry field in the flags catalog.
BUCKET_EXPIRY_FIELD: dict[str, str] = {
    "gas_cert": "Gas Certificates Expiry",
    "eicr":     "EICR Expiry",
}


def detect_renewals(payload: dict[str, Any], before: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (served_flag, doc_name, diary_type) for each certificate whose
    expiry is changing on a property where the tenant holds the superseded copy."""
    out: list[tuple[str, str, str]] = []
    for expiry_field, meta in RENEWAL_WATCH.items():
        if expiry_field not in payload:
            continue
        new_val, old_val = payload[expiry_field], before.get(expiry_field)
        if not new_val or str(new_val) == str(old_val or ""):
            continue          # cleared, or unchanged
        if before.get(meta[0]):
            out.append(meta)
    return out


def notice_for(doc_name: str) -> str:
    return (
        f"{doc_name} renewed - the tenant must be served the new copy within 28 days "
        "of the inspection. Marked as not served and added to the diary."
    )


def raise_reserve_diary(property_id: str, address: str, doc_name: str, diary_type: str) -> None:
    """Best-effort diary action telling the agent to serve the new copy."""
    today = _date.today().isoformat()
    try:
        at.create(at.TableNames.DIARY, {
            "Diary_Type": diary_type,
            "Property": [property_id],
            "Diary Date": today,
            "Alert_Date": today,   # actionable now; the legal clock runs from
                                   # the inspection, not from today
            "Alert_Message": (
                f"Serve the new {doc_name} to the tenant "
                f"(within 28 days of the inspection) - {address}"
            ),
            "Fired": False,
        })
    except Exception as e:  # noqa: BLE001 - never block the write that triggered us
        logger.warning("cert_renewal.diary_failed property=%s doc=%s err=%s",
                       property_id, doc_name, e)


def apply_expiry_update(property_id: str, expiry_field: str, new_expiry: str) -> list[str]:
    """Write a new expiry date and run the renewal side-effects in one place.

    Used by the upload route so a replacement certificate and its expiry date
    can never drift apart. Returns agent-facing notices (empty when nothing
    needed re-serving). Never raises - a bad date must not lose the upload.
    """
    if expiry_field not in RENEWAL_WATCH or not new_expiry:
        return []
    try:
        before = at.get(at.TableNames.PROPERTIES, property_id).get("fields", {})
    except Exception as e:  # noqa: BLE001
        logger.warning("cert_renewal.read_failed property=%s err=%s", property_id, e)
        return []

    payload: dict[str, Any] = {expiry_field: new_expiry}
    renewals = detect_renewals(payload, before)
    for served_flag, _doc, _dtype in renewals:
        payload[served_flag] = False

    try:
        at.update(at.TableNames.PROPERTIES, property_id, payload)
    except Exception as e:  # noqa: BLE001
        logger.warning("cert_renewal.update_failed property=%s err=%s", property_id, e)
        return []

    notices: list[str] = []
    address = before.get("Address", "")
    for _flag, doc_name, diary_type in renewals:
        raise_reserve_diary(property_id, address, doc_name, diary_type)
        notices.append(notice_for(doc_name))
    logger.info("cert_renewal.expiry_set property=%s field=%s value=%s renewals=%d",
                property_id, expiry_field, new_expiry, len(renewals))
    return notices
