"""Runtime branding — resolves to the CURRENT AGENCY's identity.

Every customer-facing artifact (emails, contract PDFs, prescribed documents,
merge fields) brands itself with the agency that owns the data, falling back
to the platform defaults from settings when no agency scope is set (system
jobs, unauthenticated paths).

Usage:
    from app.core.branding import get_brand
    b = get_brand()          # Brand for the current request's agency
    b.name, b.navy, b.gold, b.email, b.phone, b.office_address
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Brand:
    name: str
    navy: str
    gold: str
    email: str = ""
    phone: str = ""
    office_address: str = ""
    website: str = ""
    logo_url: str = ""


def _platform_brand() -> Brand:
    return Brand(
        name=settings.brand_name,
        navy=settings.brand_navy,
        gold=settings.brand_gold,
        email=settings.from_email,
    )


def brand_for_agency(agency_fields: dict) -> Brand:
    f = agency_fields or {}
    return Brand(
        name=f.get("name") or settings.brand_name,
        navy=f.get("brand_navy") or settings.brand_navy,
        gold=f.get("brand_gold") or settings.brand_gold,
        email=f.get("email") or settings.from_email,
        phone=f.get("phone") or "",
        office_address=f.get("office_address") or "",
        website=f.get("website") or "",
        logo_url=f.get("logo_url") or "",
    )


def get_brand() -> Brand:
    """Brand of the current agency scope; platform defaults otherwise.

    Reads through the db layer's TTL cache, so repeated calls within a
    request cost one lookup at most.
    """
    from app.db import supabase_client as at  # local import — avoid cycles

    aid = at.current_agency_id()
    if not aid:
        return _platform_brand()
    try:
        agency = at.get(at.TableNames.AGENCIES, aid)
    except Exception as e:  # noqa: BLE001 — branding must never break a send
        logger.warning("branding.agency_lookup_failed agency=%s err=%s", aid, e)
        return _platform_brand()
    return brand_for_agency(agency.get("fields", {}))
