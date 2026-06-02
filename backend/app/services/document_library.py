"""Document library — pre-classified catalog of templates, by stage.

The agent's "Browse document library" widget on any stage view calls
``GET /api/library?stage=N`` to get the documents pre-classified for that
stage, then ``GET /api/library/{doc_id}/prepare/{property_id}`` to load
the body + merge fields into the editor.

Two sources of content:
- **Real**: HTML files under ``backend/app/templates/library/`` (extracted from
  source .docx / .doc via ``scripts/extract_library_docs.py``).
- **Placeholder**: TPL-XX entries whose source is the master Palace Gate doc
  but whose body hasn't been imported yet. They open in the editor with a
  short placeholder body so the agent can still pick them and we can wire
  the workflow end-to-end. Replace with real content as templates land.

The default "mode" on each entry suggests which action the editor should
default to (sign / email-pdf / email-html), but the agent is free to override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

DocMode = Literal["sign", "email_pdf", "email_html"]
DocSource = Literal["library_file", "master_doc"]


_LIBRARY_DIR = Path(__file__).resolve().parent.parent / "templates" / "library"


@dataclass(frozen=True)
class LibraryDoc:
    id: str
    name: str
    stage: int                 # 1–9, matches frontend stages.ts
    default_mode: DocMode
    source: DocSource
    body_file: Optional[str] = None  # filename under templates/library/
    placeholder_body: Optional[str] = None
    signers: list[str] = field(default_factory=list)   # roles, e.g. ["Landlord"], ["Landlord","Tenant"]
    description: str = ""
    # Filter — only show this doc when the property's `Tenancy Type` matches
    # one of these values. ``None`` means "show always". Used today to hide
    # the APT TA when the property is Common Law (and vice versa). Future
    # filters (HMO_Flag, residency, Westminster_Flag) follow the same pattern.
    tenancy_types: Optional[list[str]] = None
    # Anchor strings that the signing provider (DocuSign) uses to place
    # signature fields inside the rendered PDF. ``None`` means "use the
    # global defaults ['/sig1/', '/sig2/']" — fine for docs that bake those
    # markers into the source. Override per-doc when the markers differ.
    anchor_strings: Optional[list[str]] = None


def _load_body(filename: str) -> str:
    """Read an extracted library HTML file. Returns empty string on miss."""
    p = _LIBRARY_DIR / filename
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _placeholder_body(name: str, tpl_id: str) -> str:
    return (
        f"<h2>{name}</h2>"
        f"<p><em>Template <strong>{tpl_id}</strong> content has not been imported yet.</em></p>"
        "<p>Edit this body to add the correspondence text, then send it via one of the three editor actions:</p>"
        "<ul>"
        "<li><strong>Sign</strong> — render to PDF and send to DocuSeal for signature.</li>"
        "<li><strong>Send as PDF attachment</strong> — render to PDF and email with a custom cover note.</li>"
        "<li><strong>Send as email</strong> — send the edited body as the email itself.</li>"
        "</ul>"
        "<p>Merge fields like <code>{{landlord_full_name}}</code> are interpolated at send time.</p>"
    )


# ---------------------------------------------------------------------------
# Catalog. Each row is one document the library will surface.
#
# Stage mapping notes (per master Palace Gate doc + user instruction):
#   1 Take-on        — TPL-01 Intro Valuation, TPL-02 Instruction, TPL-04 T&C Reminder
#   2 Compliance     — TPL-03 KYC + TPL-07 Legal Reqs + TPL-08 Pre-Tenancy Works
#                      + PG T&C 2026 (user-supplied)
#   3 Marketing      — (no TPL — handled by photo/portal UI)
#   4 Offer          — TPL-05 Offer Confirmation, TPL-06 Referencing Request
#   5 Referencing    — TPL-06 (re-served reminder)
#   6 TA Signing     — APT Pet ABNB (user-supplied APT TA), Common-Law TA (user-supplied)
#   7 Pre Move-in    — TPL-09 Bank/SO, TPL-10 Check-In, TPL-11 Welcome Pack,
#                      TPL-12 Move-In Confirm, TPL-13 Utility Transfer
#   8 Live Tenancy   — TPL-14..31 (rent reminders, maintenance, periodic)
#   9 End of Tenancy — TPL-32..42 (renewal, notices, deposit, farewell)
# ---------------------------------------------------------------------------
_CATALOG: list[LibraryDoc] = []


def _add(*args, **kwargs) -> None:
    _CATALOG.append(LibraryDoc(*args, **kwargs))


def _tpl(tpl_id: str, name: str, stage: int, mode: DocMode = "email_html", signers: list[str] | None = None) -> None:
    """Register a TPL.

    If a matching file exists under ``templates/library/<id>.html`` (extracted
    by ``scripts/extract_master_tpls.py`` from the master Palace Gate doc), the
    entry is registered as ``library_file`` and the body is loaded from disk.
    Otherwise it falls back to a placeholder body that still renders in the
    editor so the workflow keeps working.
    """
    doc_id = tpl_id.lower().replace("-", "_")
    body_filename = f"{doc_id}.html"
    body_exists = (_LIBRARY_DIR / body_filename).exists()
    _add(
        id=doc_id,
        name=f"{tpl_id} — {name}",
        stage=stage,
        default_mode=mode,
        source="library_file" if body_exists else "master_doc",
        body_file=body_filename if body_exists else None,
        placeholder_body=None if body_exists else _placeholder_body(name, tpl_id),
        signers=signers or [],
        description="Master Palace Gate correspondence library.",
    )


# --- User-supplied library files (real content) -----------------------------
_add(
    id="pg_tcs_2026",
    name="Palace Gate Terms & Conditions 2026",
    stage=2,
    default_mode="sign",
    source="library_file",
    body_file="pg_tcs_2026.html",
    signers=["Landlord"],
    # Two anchor markers are physically baked into the PDF body. DocuSign
    # drops the signHere tab at /sig1/ for the first signer and /sig2/ for
    # the second; with one signer the /sig2/ marker stays as literal text.
    anchor_strings=["/sig1/", "/sig2/"],
    description="Current Palace Gate Terms & Conditions of Business. Compliance stage — must be signed by the landlord before money moves.",
)
_add(
    id="apt_pet_abnb",
    name="Assured Periodic Tenancy (Pet / ABNB variant)",
    stage=6,
    default_mode="sign",
    source="library_file",
    body_file="apt_pet_abnb.html",
    signers=["Landlord", "Tenant"],
    description="APT tenancy agreement, current variant covering pet and short-let restrictions.",
    tenancy_types=["APT"],   # only relevant when the property is APT
    # Four distinct signing anchors baked into the execution block of the body
    # (Landlord / Tenant / Guarantor / Witness). Without this the default
    # ["/sig1/","/sig2/"] would wrap a 3rd/4th signer back onto the first two
    # markers, stacking tabs. See the execution block in apt_pet_abnb.html.
    anchor_strings=["/sig1/", "/sig2/", "/sig3/", "/sig4/"],
)
_add(
    id="common_law_ta",
    name="Common Law Tenancy Agreement (Dec 2020)",
    stage=6,
    default_mode="sign",
    source="library_file",
    body_file="common_law_ta.html",
    signers=["Landlord", "Tenant"],
    description="Common-law tenancy agreement for annual rents >£100k (not Housing-Act covered).",
    tenancy_types=["Common Law"],  # only relevant when the property is Common Law
    # Body carries /sig1/../sig5/ (LL x2, TT, Guarantor x2). Map them so extra
    # signers don't wrap onto the first two anchors.
    anchor_strings=["/sig1/", "/sig2/", "/sig3/", "/sig4/", "/sig5/"],
)

# --- All 44 TPLs from the master doc, mapped to stages ----------------------
# Stage 1 — Take-on
_tpl("TPL-01", "Introductory Valuation Letter",   1, "email_pdf")
_tpl("TPL-02", "Instruction Letter",              1, "sign", signers=["Landlord"])
_tpl("TPL-04", "T&C Reminder",                    1, "email_html")

# Stage 2 — Compliance
_tpl("TPL-03", "KYC Request & AML Checklist",     2, "email_html")
_tpl("TPL-07", "Legal Requirements & Pre-Tenancy Checklist to Landlord", 2, "email_pdf")
_tpl("TPL-08", "Pre-Tenancy Works Sign-Off Request", 2, "email_pdf")

# Stage 4 — Offer
_tpl("TPL-05", "Offer Confirmation to Landlord",  4, "email_pdf")
_tpl("TPL-06", "Referencing Request to Tenant",   4, "email_html")

# Stage 7 — Pre Move-in
_tpl("TPL-09", "Bank Details & Standing Order Instruction", 7, "email_pdf")
_tpl("TPL-10", "Check-In Confirmation to Tenant", 7, "email_html")
_tpl("TPL-11", "Welcome Letter & Full Tenant Pack", 7, "email_pdf")
_tpl("TPL-12", "Move-In Confirmation to Landlord", 7, "email_html")
_tpl("TPL-13", "Utility Transfer Instruction to Tenant (GDPR-Compliant)", 7, "email_pdf")

# Stage 8 — Live tenancy (rent / maintenance / periodic touches)
_tpl("TPL-14", "Friendly Rent Reminder (Day -3)", 8, "email_html")
_tpl("TPL-15", "First Arrears Notice (Day 8)",    8, "email_pdf")
_tpl("TPL-16", "Second Arrears Notice (Day 14)",  8, "email_pdf")
_tpl("TPL-17", "Final Arrears Warning (Day 21)",  8, "email_pdf")
_tpl("TPL-18", "Maintenance Acknowledgement to Tenant", 8, "email_html")
_tpl("TPL-19", "Maintenance Notification to Landlord", 8, "email_html")
_tpl("TPL-20", "Works Instruction to Contractor", 8, "email_pdf")
_tpl("TPL-21", "Contractor Chase",                8, "email_html")
_tpl("TPL-22", "Works Completion Notice to Tenant", 8, "email_html")
_tpl("TPL-23", "Works Completion Report to Landlord", 8, "email_pdf")
_tpl("TPL-24", "Inspection Report Cover Letter to Landlord", 8, "email_pdf")
_tpl("TPL-25", "Month-1 Settling-In Check",       8, "email_html")
_tpl("TPL-26", "Six-Month Check-In",              8, "email_html")
_tpl("TPL-27", "London Lifestyle Newsletter / Market Update", 8, "email_html")
_tpl("TPL-28", "Palace Gate Services Introduction to Tenant", 8, "email_html")
_tpl("TPL-29", "Tenancy Anniversary Note",        8, "email_html")
_tpl("TPL-30", "Landlord Market Update",          8, "email_html")
_tpl("TPL-31", "Landlord Proactive Property Health Summary", 8, "email_pdf")

# Stage 9 — End of tenancy
_tpl("TPL-32", "Renewal Prompt to Landlord",      9, "email_html")
_tpl("TPL-33", "Renewal Prompt to Tenant",        9, "email_html")
_tpl("TPL-34", "Renewal Confirmation to Both Parties", 9, "email_pdf")
_tpl("TPL-35a", "Notice to Quit — APT — Tenant Serving Notice", 9, "email_pdf")
_tpl("TPL-35b", "Section 8 Notice — APT — Landlord Seeking Possession", 9, "email_pdf")
_tpl("TPL-35c", "Notice to Vacate — Common Law Tenancy", 9, "email_pdf")
_tpl("TPL-36", "End of Tenancy Information Pack to Tenant", 9, "email_pdf")
_tpl("TPL-37", "Check-Out Reminder & Cleaning Guidance", 9, "email_html")
_tpl("TPL-38", "Check-Out Cover Letter to Landlord", 9, "email_html")
_tpl("TPL-39", "Check-Out Cover Letter to Tenant", 9, "email_html")
_tpl("TPL-40", "Deposit Release Confirmation",    9, "email_pdf")
_tpl("TPL-41", "Deposit Dispute Notification",    9, "email_pdf")
_tpl("TPL-42", "Farewell & Future Relationship Note to Tenant", 9, "email_html")


_BY_ID: dict[str, LibraryDoc] = {d.id: d for d in _CATALOG}


def list_documents(
    stage: Optional[int] = None,
    *,
    tenancy_type: Optional[str] = None,
) -> list[LibraryDoc]:
    """Return library entries.

    ``stage`` — narrows to one stage (1–9).
    ``tenancy_type`` — drops documents whose ``tenancy_types`` filter excludes
    the current property (e.g. hides the APT TA on a Common Law property).
    ``None`` means "no filter".
    """
    docs = _CATALOG if stage is None else [d for d in _CATALOG if d.stage == stage]
    if tenancy_type:
        docs = [d for d in docs if (d.tenancy_types is None or tenancy_type in d.tenancy_types)]
    return list(docs)


def get_document(doc_id: str) -> Optional[LibraryDoc]:
    return _BY_ID.get(doc_id)


def get_body(doc: LibraryDoc) -> str:
    """Resolve the editable body for a library document."""
    if doc.source == "library_file" and doc.body_file:
        body = _load_body(doc.body_file)
        if body:
            return body
    return doc.placeholder_body or f"<h2>{doc.name}</h2><p>(empty)</p>"
