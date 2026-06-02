"""PG_05 — Tenant pack / pre-move-in (spec §6.6).

Generates the standard prescribed documents as PDFs, attaches them to a single
email to the tenant, persists each served PDF under
``uploads/<property_id>/served_<doc_key>/<timestamp>.pdf``, and writes a
Compliance audit row per document.

Per the master Palace Gate doc: prescribed documents MUST be PDF attachments,
never links — non-service blocks possession proceedings and (for the RRA sheet)
risks a £7,000 fine per breach.

For gas_cert / epc / eicr we prefer the landlord's actual uploaded PDF (lives
in ``uploads/<property_id>/<bucket>/``) over the generated placeholder, so the
tenant receives the genuine certificate. Falls back to a placeholder only if
no upload exists.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime
from pathlib import Path

from app.config import settings
from app.core.email_client import render, send_email
from app.core.logger import get_logger
from app.db import airtable_client as at
from app.handlers.pg00_gate import evaluate_gate, find_stage_agent_email
from app.routers.uploads import UPLOADS_ROOT, _public_url
from app.services.prescribed_docs import (
    DOC_DEFS,
    render_prescribed_pdf,
    standard_tenant_pack_docs,
)

logger = get_logger(__name__)


# Map prescribed-doc keys → the Properties boolean field that records service.
_SERVED_FLAGS: dict[str, str] = {
    "how_to_rent":    "How_To_Rent_Served",
    "gas_cert":       "Gas_Cert_Served",
    "epc":            "EPC_Served",
    "eicr":           "EICR_Served",
    "prescribed_info": "TDS_Info_Served",
    "rra_sheet":      "RRA_Sheet_Served",
}

# Prescribed-doc keys whose source-of-truth is a landlord-uploaded file. When
# present, the uploaded PDF is attached instead of the generated placeholder.
_UPLOAD_BUCKET_FOR_DOC: dict[str, str] = {
    "gas_cert": "gas_cert",
    "epc":      "epc",
    "eicr":     "eicr",
}


def _latest_pdf_in_bucket(property_id: str, bucket: str) -> tuple[Path | None, str | None]:
    """Return (path, public_url) of the most-recently-uploaded PDF in a bucket.

    Files in a bucket are timestamped (``YYYYMMDDHHMMSS_<nonce>_<orig>``) so
    lexicographic max is also chronological max. Returns (None, None) if
    the bucket is empty or contains no PDFs.
    """
    bucket_dir = UPLOADS_ROOT / property_id / bucket
    if not bucket_dir.exists():
        return None, None
    pdfs = [p for p in bucket_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
    if not pdfs:
        return None, None
    latest = max(pdfs, key=lambda p: p.name)
    return latest, _public_url(property_id, bucket, latest.name)


def _persist_served_pdf(property_id: str, doc_key: str, pdf_bytes: bytes) -> str:
    """Save a served PDF to disk under the property's uploads dir; return URL."""
    bucket = f"served_{doc_key}"
    target_dir = UPLOADS_ROOT / property_id / bucket
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    nonce = secrets.token_hex(4)
    filename = f"{stamp}_{nonce}_{doc_key}.pdf"
    (target_dir / filename).write_bytes(pdf_bytes)
    return _public_url(property_id, bucket, filename)


async def handle_tenant_pack(property_id: str) -> dict:
    prop = at.get(at.TableNames.PROPERTIES, property_id)
    pfields = prop.get("fields", {})
    address = pfields.get("Address", "")
    is_apt = pfields.get("Tenancy Type") == "APT"

    # Collect every tenant on the property (HMO / multi-tenant support — step 26).
    tenant_ids: list[str] = pfields.get("Tenant") or []
    tenants: list[dict] = []
    for tid in tenant_ids:
        try:
            tf = at.get(at.TableNames.TENANTS, tid).get("fields", {})
            tenants.append({"id": tid, "email": tf.get("Tenant Email"), "name": tf.get("Name")})
        except Exception as e:  # noqa: BLE001
            logger.warning("tenant_pack.tenant_fetch_failed id=%s err=%s", tid, e)

    primary_name = tenants[0]["name"] if tenants else None

    # 1. Build the attachment set for the pack.
    # For gas_cert / epc / eicr, prefer the landlord's actual uploaded PDF
    # (mandated by the master Palace Gate doc — placeholder PDFs are NOT
    # legally valid certs). Fall back to the placeholder only if nothing was
    # uploaded so the pack still goes out with a visible warning to the agent.
    served: list[dict] = []
    attachments: list[dict] = []
    missing_real_pdf: list[str] = []
    for key in standard_tenant_pack_docs(is_apt=is_apt):
        doc = DOC_DEFS[key]
        bucket = _UPLOAD_BUCKET_FOR_DOC.get(key)
        latest_path, latest_url = (None, None)
        if bucket:
            latest_path, latest_url = _latest_pdf_in_bucket(property_id, bucket)

        if latest_path is not None:
            # Attach the genuine uploaded certificate.
            pdf_bytes = latest_path.read_bytes()
            served.append({
                "key": key, "doc": doc, "url": latest_url, "bytes": pdf_bytes,
                "source": "uploaded",
            })
            attachments.append({
                "filename": f"{doc.compliance_type.replace(' ', '_')}.pdf",
                "content": pdf_bytes,
                "mime": "application/pdf",
            })
            logger.info("tenant_pack.attached_uploaded key=%s file=%s", key, latest_path.name)
        else:
            if bucket:
                # Bucket exists in our model but landlord never uploaded —
                # surface this so the agent can fix it before re-sending.
                missing_real_pdf.append(key)
            try:
                doc, pdf_bytes = render_prescribed_pdf(
                    key, property_address=address, tenant_name=primary_name,
                )
                file_url = _persist_served_pdf(property_id, key, pdf_bytes)
                served.append({"key": key, "doc": doc, "url": file_url, "bytes": pdf_bytes,
                               "source": "placeholder"})
                attachments.append({
                    "filename": f"{doc.compliance_type.replace(' ', '_')}.pdf",
                    "content": pdf_bytes,
                    "mime": "application/pdf",
                })
            except Exception as e:  # noqa: BLE001
                logger.error("tenant_pack.pdf_render_failed key=%s err=%s", key, e)

    # 2. Send the pack to every named tenant on the tenancy.
    sent_to: list[str] = []
    if attachments and tenants:
        html = render("E09_tenant_pack.html", **{
            "property_address": address,
            "is_apt": is_apt,
            "doc_summary": [{"title": s["doc"].title} for s in served],
        })
        for t in tenants:
            if not t["email"]:
                continue
            try:
                await send_email(
                    t["email"],
                    subject=f"Your move-in pack — {address}",
                    html=html,
                    attachments=attachments,
                )
                sent_to.append(t["email"])
            except Exception as e:  # noqa: BLE001
                logger.warning("tenant_pack.send_failed to=%s err=%s", t["email"], e)

    # 3. Flip the boolean served-flags on the Property record.
    today_iso = date.today().isoformat()
    flag_update: dict = {}
    for s in served:
        flag = _SERVED_FLAGS.get(s["key"])
        if flag:
            flag_update[flag] = True
    if "rra_sheet" in {s["key"] for s in served}:
        flag_update["RRA_sheet_served_date"] = today_iso
    if flag_update:
        at.update(at.TableNames.PROPERTIES, property_id, flag_update)

    # 4. Write a Compliance audit row per document — links all tenants so
    #    multi-tenant tenancies have a complete service trail.
    served_to_str = ", ".join(sent_to) if sent_to else ""
    from app.services.sent_documents import record_sent  # noqa: PLC0415
    for s in served:
        try:
            fields: dict = {
                "Document_Type": s["doc"].compliance_type,
                "Property": [property_id],
                "Served_Date": today_iso,
                "Served_To": served_to_str,
                "Served_As": "PDF Attachment",
                "File_URL": s["url"],
                "Confirmed_Sent": bool(sent_to),
            }
            if tenant_ids:
                fields["Tenant"] = tenant_ids
            at.create(at.TableNames.COMPLIANCE, fields)
        except Exception as e:  # noqa: BLE001
            logger.warning("compliance.create_failed doc=%s err=%s", s["key"], e)
        # Also record it in Sent_Documents so the prescribed pack shows up in
        # the per-stage sent view (Stage 7), alongside library letters.
        try:
            record_sent(
                property_id=property_id,
                doc_id=f"served_{s['key']}",
                doc_name=s["doc"].title,
                stage=7,
                channel="Attachment",
                recipients=sent_to or None,
                pdf_url=s["url"],
                sent_by="system",
                status="Sent",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("sent_doc.tenant_pack_record_failed doc=%s err=%s", s["key"], e)

    # 5. Notify agent
    agent_email = find_stage_agent_email(7)
    if agent_email:
        try:
            html = render("E10_pack_sent.html", property_address=address)
            await send_email(agent_email, subject=f"Tenant pack sent — {address}", html=html)
        except Exception as e:  # noqa: BLE001
            logger.warning("agent_summary.send_failed err=%s", e)

    # 6. Re-evaluate gate (pre-move-in → live tenancy).
    gate = await evaluate_gate(property_id, target_stage=8)

    return {
        "property_id": property_id,
        "sent_to": sent_to,
        "documents_served": [
            {"key": s["key"], "type": s["doc"].compliance_type, "url": s["url"], "source": s.get("source", "placeholder")}
            for s in served
        ],
        "missing_real_pdf": missing_real_pdf,
        "gate": gate.to_dict(),
    }
