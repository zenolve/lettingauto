"""Contract editor + DocuSeal pipeline.

Endpoints:
  GET  /api/contracts/templates                          List bundled templates
  GET  /api/contracts/{property_id}/prepare/{template}   Get prefilled HTML + merge fields
  POST /api/contracts/{property_id}/submit               Body has edited HTML + signing roles.
                                                          We HTML→PDF→DocuSeal.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.core.auth import Agent, require_agent
from app.core.docuseal_client import create_pdf_submission
from app.core.logger import get_logger
from app.core.pdf_renderer import html_to_pdf, render_contract_html, render_template_to_html
from app.db import airtable_client as at
from app.services.merge_fields import MERGE_FIELD_CATALOGUE, build_merge_context

router = APIRouter(prefix="/api/contracts", tags=["contracts"])
logger = get_logger(__name__)


# Catalogue of bundled templates the user can pick from.
TEMPLATES: dict[str, dict] = {
    "tc": {
        "key": "tc",
        "name": "Terms & Conditions",
        "file": "t_and_c.html",
        "signers": ["Landlord"],
    },
    "offer": {
        "key": "offer",
        "name": "Offer Letter",
        "file": "offer_letter.html",
        "signers": ["Landlord"],
    },
    "ta": {
        "key": "ta",
        "name": "Tenancy Agreement",
        "file": "tenancy_agreement.html",
        "signers": ["Landlord", "Tenant"],
    },
}


@router.get("/templates")
def list_templates(_: Agent = Depends(require_agent)) -> dict:
    return {
        "templates": list(TEMPLATES.values()),
        "merge_fields": MERGE_FIELD_CATALOGUE,
    }


@router.get("/{property_id}/prepare/{template_key}")
def prepare(
    property_id: str,
    template_key: str,
    _: Agent = Depends(require_agent),
) -> dict[str, Any]:
    if template_key not in TEMPLATES:
        raise HTTPException(404, f"Unknown template: {template_key}")
    template = TEMPLATES[template_key]
    ctx = build_merge_context(property_id)
    body_html = render_template_to_html(template["file"], **ctx)
    return {
        "template": template,
        "merge_fields": ctx,
        "merge_field_catalogue": MERGE_FIELD_CATALOGUE,
        "body_html": body_html,
    }


class Submitter(BaseModel):
    role: str = Field(..., examples=["Landlord", "Tenant"])
    name: str
    email: EmailStr


class ContractSubmit(BaseModel):
    template_key: str
    title: str
    body_html: str
    submitters: list[Submitter]


@router.post("/{property_id}/submit")
async def submit_contract(
    property_id: str,
    body: ContractSubmit,
    _: Agent = Depends(require_agent),
) -> dict[str, Any]:
    if body.template_key not in TEMPLATES:
        raise HTTPException(400, f"Unknown template: {body.template_key}")

    # 1. Final interpolation pass — replace any remaining {{merge_field}} tokens
    #    with current Airtable values before rendering to PDF.
    merge_ctx = build_merge_context(property_id)
    final_body = _interpolate_merge_fields(body.body_html, merge_ctx)

    # 2. Wrap the edited body in the branded shell
    html = render_contract_html(final_body, title=body.title)

    # 2. Render to PDF
    try:
        pdf_bytes = html_to_pdf(html)
    except Exception as e:  # noqa: BLE001
        logger.error("pdf.render_failed err=%s", e)
        raise HTTPException(500, "Failed to render PDF — check WeasyPrint installation.")

    # 3. Push to DocuSeal
    submitters_payload = [
        {"role": s.role, "name": s.name, "email": s.email}
        for s in body.submitters
    ]
    docuseal = await create_pdf_submission(
        name=body.title,
        pdf_bytes=pdf_bytes,
        submitters=submitters_payload,
        send_email=True,
        metadata={
            "property_id": property_id,
            "template_key": body.template_key,
            "kind": _kind_for_template(body.template_key),
        },
    )

    # 4. Record on the Submissions audit table
    at.create(at.TableNames.SUBMISSIONS, {
        "Form Name": f"Contract: {body.title}",
        "Property": [property_id],
        "JSON Data": str({"submitters": submitters_payload, "docuseal_id": docuseal.get("id")}),
    })

    return {"docuseal": docuseal, "title": body.title}


def _kind_for_template(key: str) -> str:
    return {
        "tc": "T&C",
        "offer": "Offer Letter",
        "ta": "Tenancy Agreement",
    }.get(key, key)


_MERGE_TOKEN = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.IGNORECASE)


def _interpolate_merge_fields(html: str, ctx: dict[str, Any]) -> str:
    """Replace any remaining `{{key}}` tokens with values from `ctx`.

    Tokens whose key isn't in ctx are left untouched so they're visible in the
    rendered PDF — that way nothing fails silently.
    """
    def repl(m: re.Match) -> str:
        key = m.group(1)
        v = ctx.get(key)
        return str(v) if v is not None else m.group(0)
    return _MERGE_TOKEN.sub(repl, html)
