"""PG_07 — Renters Rights Act batch (spec §6.8).

On-demand workflow that serves the RRA information sheet as a **PDF
attachment** to every active APT tenant who hasn't already received it.

Master doc CRITICAL DEADLINE: 31 May 2026 — every active APT tenant must
have been served the RRA sheet by this date. Fine up to £7,000 per breach.
"""
from __future__ import annotations

from datetime import date

from app.config import settings
from app.core.email_client import render, send_email
from app.core.logger import get_logger
from app.db import airtable_client as at
from app.handlers.pg05_tenant_pack import _persist_served_pdf
from app.services.prescribed_docs import render_prescribed_pdf

logger = get_logger(__name__)


async def handle_rra_batch() -> dict:
    """Generate + serve the RRA PDF to every APT tenancy not yet served."""
    # Properties of Tenancy Type "APT" that haven't been flagged as served.
    formula = at.and_(
        at.eq("Tenancy Type", "APT"),
        # NOT() handles both "false" and "unset" on the checkbox.
        f"NOT({{RRA_Sheet_Served}})",
    )
    props = at.search(at.TableNames.PROPERTIES, formula=formula)
    served: list[str] = []
    failed: list[dict] = []

    for p in props:
        pid = p["id"]
        f = p.get("fields", {})
        address = f.get("Address", "")
        tenant_ids = f.get("Tenant") or []
        if not tenant_ids:
            failed.append({"property_id": pid, "reason": "no tenant linked"})
            continue
        try:
            # Render the RRA PDF once per property, then serve to every named
            # tenant on the tenancy (multi-tenant / HMO support — step 26).
            primary = at.get(at.TableNames.TENANTS, tenant_ids[0]).get("fields", {})
            doc, pdf_bytes = render_prescribed_pdf(
                "rra_sheet",
                property_address=address,
                tenant_name=primary.get("Name"),
            )
            file_url = _persist_served_pdf(pid, "rra_sheet", pdf_bytes)
            html = render("E09_rra_sheet.html", property_address=address)

            sent_to: list[str] = []
            for tid in tenant_ids:
                try:
                    tf = at.get(at.TableNames.TENANTS, tid).get("fields", {})
                    email = tf.get("Tenant Email")
                    if not email:
                        continue
                    await send_email(
                        email,
                        subject="Renters' Rights Act 2025 — important information for your tenancy",
                        html=html,
                        attachments=[{
                            "filename": "RRA_Information_Sheet.pdf",
                            "content": pdf_bytes,
                            "mime": "application/pdf",
                        }],
                    )
                    sent_to.append(email)
                except Exception as te:  # noqa: BLE001
                    logger.warning("rra.tenant_send_failed property=%s tenant=%s err=%s", pid, tid, te)

            if not sent_to:
                failed.append({"property_id": pid, "reason": "no tenant emails"})
                continue

            at.update(at.TableNames.PROPERTIES, pid, {
                "RRA_Sheet_Served": True,
                "RRA_sheet_served_date": date.today().isoformat(),
            })
            try:
                at.create(at.TableNames.COMPLIANCE, {
                    "Document_Type": "RRA Sheet",
                    "Property": [pid],
                    "Tenant": tenant_ids,
                    "Served_Date": date.today().isoformat(),
                    "Served_To": ", ".join(sent_to),
                    "Served_As": "PDF Attachment",
                    "File_URL": file_url,
                    "Confirmed_Sent": True,
                })
            except Exception as ce:  # noqa: BLE001
                logger.warning("rra.compliance_create_failed property=%s err=%s", pid, ce)
            served.append(pid)
        except Exception as e:  # noqa: BLE001
            logger.warning("rra.serve_failed property=%s err=%s", pid, e)
            failed.append({"property_id": pid, "reason": str(e)})

    # Summary to admin
    html = render(
        "E11_generic.html",
        diary={
            "Type": "RRA Batch summary",
            "served": served,
            "failed": failed,
        },
    )
    try:
        await send_email(settings.admin_email, subject=f"RRA batch complete: {len(served)} served / {len(failed)} failed", html=html)
    except Exception as e:  # noqa: BLE001
        logger.warning("rra.admin_summary_failed err=%s", e)
    return {"served": served, "failed": failed}
