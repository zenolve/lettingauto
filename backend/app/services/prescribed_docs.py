"""Prescribed-document PDF generation for the tenant pack.

The master compliance doc is emphatic that prescribed documents MUST be sent
as PDF attachments, not as links — non-service can block possession proceedings
and (for the RRA Information Sheet) trigger a £7,000 fine per breach.

While the real source PDFs (How to Rent handbook, RRA info sheet, Form 4A,
gas/EPC/EICR certs) live in the templates pipeline that's still being built,
this module generates branded placeholder PDFs that can already be attached
and served. Each PDF clearly labels itself as a placeholder so it's never
confused for the real document in a real handover.

Replace the placeholder bodies in ``DOC_DEFS`` with real content (or load real
source PDFs from disk) when the templates work lands.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.config import settings
from app.core.logger import get_logger
from app.core.pdf_renderer import html_to_pdf

logger = get_logger(__name__)


_UNICODE_ASCII_MAP = {
    "—": "--",   # em-dash
    "–": "-",    # en-dash
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    " ": " ",
    "£": "GBP ", # pound — Helvetica core does NOT include this codepoint
    "€": "EUR ",
    "•": "*",
    "→": "->",
}


def _ascii_safe(s: str) -> str:
    """Strip / replace characters fpdf2's core Helvetica can't render."""
    for k, v in _UNICODE_ASCII_MAP.items():
        s = s.replace(k, v)
    # Drop anything else outside Latin-1 to avoid the same render-fail.
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _fpdf_fallback(*, title: str, legislation: str, body_html: str, property_address: str, tenant_name: str | None) -> bytes:
    """Pure-Python PDF fallback used when WeasyPrint's native deps are missing.

    Renders the same logical content as the HTML version using fpdf2 with the
    built-in Helvetica font, which is Latin-1 only — Unicode (em-dashes, smart
    quotes, etc.) is normalised to ASCII via ``_ascii_safe`` first.
    """
    from fpdf import FPDF  # local import — fpdf2 only required for the fallback path

    pdf = FPDF(format="A4")
    pdf.set_margins(left=15, top=15, right=15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    navy = (0, 0x4A, 0xAD)
    gold = (0xC9, 0xA2, 0x4C)

    # Header band
    pdf.set_fill_color(*navy)
    pdf.rect(0, 0, 210, 16, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(15, 5)
    from app.core.branding import get_brand  # local import — agency-branded header
    pdf.cell(0, 6, _ascii_safe(f"PRESCRIBED DOCUMENT - SERVED VIA {get_brand().name.upper()}"), ln=1)
    pdf.set_text_color(0, 0, 0)

    # Title
    pdf.set_xy(15, 22)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*navy)
    pdf.multi_cell(180, 8, _ascii_safe(title))
    pdf.set_draw_color(*gold)
    pdf.set_line_width(0.8)
    y = pdf.get_y() + 1
    pdf.line(15, y, 195, y)

    pdf.set_y(pdf.get_y() + 4)
    pdf.set_text_color(0x6B, 0x72, 0x80)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(180, 5, _ascii_safe(legislation))

    pdf.set_y(pdf.get_y() + 4)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(180, 6, _ascii_safe(f"Property: {property_address}"))
    if tenant_name:
        pdf.multi_cell(180, 6, _ascii_safe(f"Tenant: {tenant_name}"))
    pdf.multi_cell(180, 6, f"Served on: {date.today().isoformat()}")

    pdf.set_y(pdf.get_y() + 4)
    import re
    plain = re.sub(r"<[^>]+>", "", body_html).strip()
    plain = re.sub(r"\s+", " ", plain)
    pdf.multi_cell(180, 6, _ascii_safe(plain))

    return bytes(pdf.output())


@dataclass(frozen=True)
class DocDef:
    """A prescribed document the system can generate and serve."""

    key: str
    """Stable identifier used in handlers/log lines (e.g. ``how_to_rent``)."""

    compliance_type: str
    """Exact ``Document_Type`` singleSelect option in Airtable Compliance."""

    title: str
    legislation: str
    body_html: str


# ---------------------------------------------------------------------------
# Document catalogue — keep ``compliance_type`` aligned with the live
# Airtable Compliance.Document_Type options:
#   Gas Cert | EPC | How to Rent | Section 8 Notice | Section 21 Notice |
#   Deposit Certificate | Prescribed Info | Other | EICR | RRA Sheet |
#   Ground 4A Notice
# ---------------------------------------------------------------------------
DOC_DEFS: dict[str, DocDef] = {
    "how_to_rent": DocDef(
        key="how_to_rent",
        compliance_type="How to Rent",
        title="How to Rent — the checklist for renting in England",
        legislation="Deregulation Act 2015; Housing Act 1988 (as amended)",
        body_html=(
            "<p>This document is the current edition of the government 'How to Rent — the checklist for renting in England' handbook.</p>"
            "<p><em>[Placeholder — replace with the latest version from gov.uk/how-to-rent. The actual handbook will be substituted automatically once the templates pipeline (TPL series) is in place.]</em></p>"
        ),
    ),
    "gas_cert": DocDef(
        key="gas_cert",
        compliance_type="Gas Cert",
        title="Gas Safety Certificate (CP12)",
        legislation="Gas Safety (Installation & Use) Regulations 1998",
        body_html=(
            "<p>The Gas Safety Certificate covering all gas appliances at the property has been issued and is on file.</p>"
            "<p><em>[Placeholder — the actual signed CP12 PDF supplied by the Gas Safe engineer is attached separately or stored against the property in Airtable.]</em></p>"
        ),
    ),
    "epc": DocDef(
        key="epc",
        compliance_type="EPC",
        title="Energy Performance Certificate (EPC)",
        legislation="Energy Performance of Buildings (England and Wales) Regulations 2012",
        body_html=(
            "<p>The current EPC for the property is on file. The minimum legal rating for a let property is E.</p>"
            "<p><em>[Placeholder — the actual EPC PDF supplied via the EPC register is attached separately or stored against the property in Airtable.]</em></p>"
        ),
    ),
    "eicr": DocDef(
        key="eicr",
        compliance_type="EICR",
        title="Electrical Installation Condition Report (EICR)",
        legislation="Electrical Safety Standards in the Private Rented Sector Regulations 2020",
        body_html=(
            "<p>The current EICR for the property is on file. Renewal is required every five years (or as stated in the report).</p>"
            "<p><em>[Placeholder — the actual EICR PDF supplied by the qualified electrician is attached separately or stored against the property in Airtable.]</em></p>"
        ),
    ),
    "prescribed_info": DocDef(
        key="prescribed_info",
        compliance_type="Prescribed Info",
        title="Tenancy Deposit Prescribed Information",
        legislation="Housing Act 2004 s.213(5); Deregulation Act 2015",
        body_html=(
            "<p>This document records the prescribed information required when a deposit is taken for an assured periodic tenancy.</p>"
            "<p><em>[Placeholder — to be populated with the TDS prescribed-information form pre-filled with deposit amount, scheme reference, landlord and tenant details once templates pipeline is live.]</em></p>"
        ),
    ),
    "rra_sheet": DocDef(
        key="rra_sheet",
        compliance_type="RRA Sheet",
        title="Renters' Rights Act 2025 — Information for Tenants",
        legislation="Renters' Rights Act 2025 — service required for all active APT tenancies by 31 May 2026",
        body_html=(
            "<p>The Renters' Rights Act 2025 introduces significant changes to assured tenancies in England, including the abolition of fixed terms, the abolition of Section 21 'no-fault' evictions and new rights around pets and rent in advance.</p>"
            "<p><em>[Placeholder — the official government RRA Information Sheet PDF will be substituted here once stored in templates/. Failure to serve attracts a fine of up to £7,000 per breach.]</em></p>"
        ),
    ),
    "ground_4a": DocDef(
        key="ground_4a",
        compliance_type="Ground 4A Notice",
        title="Ground 4A Notice — Notice of Intent (Student Tenancies)",
        legislation="Renters' Rights Act 2025; Housing Act 1988 Schedule 2 Ground 4A",
        body_html=(
            "<p>This is a notice to the tenant(s) of the landlord's intention to rely on Ground 4A of Schedule 2 to the Housing Act 1988 (student tenancies) at the end of the academic year.</p>"
            "<p><em>[Placeholder — the prescribed Ground 4A form will be substituted here once stored in templates/. Service deadline: 31 May 2026.]</em></p>"
        ),
    ),
}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _wrap(title: str, legislation: str, body_html: str, *, property_address: str, tenant_name: str | None) -> str:
    """Wrap a prescribed-doc body in the serving agency's branded shell."""
    from app.core.branding import get_brand  # local import — avoid cycles
    b = get_brand()
    tenant_line = f"<p><strong>Tenant:</strong> {tenant_name}</p>" if tenant_name else ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<style>"
        f"  @page {{ margin: 24mm; @bottom-center {{ content: '{b.name} — ' counter(page); color: #888; font-size: 9pt; }} }}"
        "  body { font-family: Georgia, 'Times New Roman', serif; color: #1f2937; font-size: 11pt; line-height: 1.5; }"
        f"  h1 {{ color: {b.navy}; border-bottom: 3px solid {b.gold}; padding-bottom: 8px; margin-bottom: 4px; }}"
        "  .meta  { color: #6b7280; font-size: 10pt; margin-bottom: 24px; }"
        f"  .badge {{ display: inline-block; padding: 4px 10px; background: {b.navy}; color: white; font-size: 10pt; border-radius: 4px; margin-bottom: 16px; }}"
        "  em { color: #92400e; background: #fef3c7; padding: 1px 4px; }"
        "</style></head><body>"
        f"<div class='badge'>PRESCRIBED DOCUMENT — SERVED VIA {b.name.upper()}</div>"
        f"<h1>{title}</h1>"
        f"<div class='meta'>{legislation}</div>"
        f"<p><strong>Property:</strong> {property_address}</p>"
        f"{tenant_line}"
        f"<p><strong>Served on:</strong> {date.today().isoformat()}</p>"
        f"{body_html}"
        "</body></html>"
    )


def render_prescribed_pdf(
    doc_key: str,
    *,
    property_address: str,
    tenant_name: Optional[str] = None,
) -> tuple[DocDef, bytes]:
    """Render a prescribed document to PDF bytes. Returns (DocDef, pdf_bytes).

    Tries WeasyPrint first (proper HTML/CSS rendering). If WeasyPrint's
    native deps (Pango/Cairo/gobject) aren't installed — common on Windows —
    falls back to fpdf2, which is pure Python.
    """
    doc = DOC_DEFS[doc_key]
    html = _wrap(doc.title, doc.legislation, doc.body_html,
                 property_address=property_address, tenant_name=tenant_name)
    try:
        return doc, html_to_pdf(html)
    except OSError as e:
        logger.warning("prescribed_docs.weasyprint_unavailable err=%s — falling back to fpdf2", e)
        pdf_bytes = _fpdf_fallback(
            title=doc.title,
            legislation=doc.legislation,
            body_html=doc.body_html,
            property_address=property_address,
            tenant_name=tenant_name,
        )
        return doc, pdf_bytes


def standard_tenant_pack_docs(*, is_apt: bool) -> list[str]:
    """The standard list of doc keys to include in a tenant pack."""
    base = ["how_to_rent", "gas_cert", "epc", "eicr", "prescribed_info"]
    if is_apt:
        base.append("rra_sheet")
    return base
