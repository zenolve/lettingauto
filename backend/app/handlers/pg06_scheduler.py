"""PG_06 — Daily diary scheduler (spec §6.7).

Picks up all `Fired=False` diary entries whose `Alert_Date` is on or before
today, fires the appropriate email, and marks them as fired (only after the
email is sent successfully).
"""
from __future__ import annotations

from datetime import date

from app.config import settings
from app.core.email_client import render, send_email
from app.core.logger import get_logger
from app.db import supabase_client as at

logger = get_logger(__name__)


_DIARY_TYPE_TO_TEMPLATE = {
    "Rent Review S13": "E11_rent_review.html",
    "Gas Cert Renewal": "E11_gas_renewal.html",
    "EICR Renewal": "E11_eicr_renewal.html",
    "NRL Tax Cert": "E11_nrl_cert.html",
    "TDS 30-Day Countdown": "E11_tds_countdown.html",
    "Tenancy Expiry Warning": "E11_tenancy_expiry.html",
    "RTR Followup": "E11_rtr_followup.html",
    "Break Clause Info": "E11_break_clause.html",
    "RRA Deadline": "E11_rra_deadline.html",
}


async def run_scheduler(batch_size: int = 100) -> dict:
    today = date.today().isoformat()
    formula = at.and_(at.eq("Fired", False), at.is_before("Alert_Date", today))
    rows = at.search(at.TableNames.DIARY, formula=formula, max_records=batch_size)
    fired = 0
    skipped = 0
    for row in rows:
        f = row.get("fields", {})
        # Field is "Diary_Type" (singleSelect) in the live base — reading "Type"
        # always returned None, so every alert fired with the generic template
        # and a "Diary alert: None" subject. Fixed 2026-05-25.
        diary_type = f.get("Diary_Type")
        assigned = f.get("Assigned_To") or settings.admin_email
        template = _DIARY_TYPE_TO_TEMPLATE.get(diary_type, "E11_generic.html")
        # System job: the batch spans every agency. Process each row under its
        # own agency's scope so the alert email is branded correctly and the
        # write stays isolated.
        scope = at.set_agency_scope(f.get("agency_id"))
        try:
            html = render(template, diary=f)
            await send_email(
                assigned,
                subject=f"Diary alert: {diary_type}",
                html=html,
            )
            at.update(at.TableNames.DIARY, row["id"], {
                "Fired": True,
                "Fired_Date": today,
            })
            fired += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("diary.fire_failed type=%s err=%s", diary_type, e)
            skipped += 1
        finally:
            at.reset_agency_scope(scope)

    return {"fired": fired, "skipped": skipped, "checked": len(rows)}
