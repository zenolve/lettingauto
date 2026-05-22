"""Build the `{{merge_field}}` context for a contract from Airtable records."""
from __future__ import annotations

from datetime import date
from typing import Any

from app.db import airtable_client as at


def build_merge_context(property_id: str) -> dict[str, Any]:
    """Return a dict of merge values flat-keyed for templating.

    Available keys are documented inline; the frontend uses the same shape so
    the editor can show available fields in a sidebar palette.
    """
    prop = at.get(at.TableNames.PROPERTIES, property_id)
    pfields = prop.get("fields", {})

    landlord_ids = pfields.get("Landlords") or []
    landlord: dict = {}
    if landlord_ids:
        landlord = at.get(at.TableNames.LANDLORDS, landlord_ids[0]).get("fields", {})

    tenant_ids = pfields.get("Tenant") or []
    tenant: dict = {}
    if tenant_ids:
        tenant = at.get(at.TableNames.TENANTS, tenant_ids[0]).get("fields", {})

    return {
        # property
        "property_address": pfields.get("Address", ""),
        "property_post_code": pfields.get("Post Code", ""),
        "property_type": pfields.get("Property Type", ""),
        "tenancy_type": pfields.get("Tenancy Type", "Common Law"),
        "service_level": pfields.get("Service Level", ""),

        # landlord
        "landlord_full_name": landlord.get("Full Name", ""),
        "landlord_email": landlord.get("Email Address", ""),
        "landlord_mobile": landlord.get("Mobile Number", ""),
        "landlord_address": landlord.get("Full Address", ""),
        "landlord_post_code": landlord.get("Post Code", ""),
        "landlord_bank_name": landlord.get("Bank Name", ""),
        "landlord_account_name": landlord.get("Account Name", ""),
        "landlord_sort_code": landlord.get("Sort Code", ""),
        "landlord_account_number": landlord.get("Account Number", ""),

        # tenant
        "tenant_full_name": tenant.get("Name", ""),
        "tenant_email": tenant.get("Tenant Email", ""),
        "tenant_address": tenant.get("Tenant Address", ""),
        "tenancy_start_date": tenant.get("Start Date", ""),
        "tenancy_end_date": tenant.get("End Date", "") or "Periodic",
        "tenancy_term": tenant.get("Tenancy Term", ""),
        "monthly_rent": tenant.get("Amount", ""),
        "deposit_amount": tenant.get("Deposit Amount", ""),
        "holding_deposit": tenant.get("Holding_Deposit", ""),

        # meta
        "today": date.today().isoformat(),
    }


# Catalogue exposed to the frontend so users see what fields exist.
MERGE_FIELD_CATALOGUE: list[dict] = [
    {"group": "Property", "key": "property_address", "label": "Property address"},
    {"group": "Property", "key": "property_post_code", "label": "Property postcode"},
    {"group": "Property", "key": "property_type", "label": "Property type"},
    {"group": "Property", "key": "tenancy_type", "label": "Tenancy type"},
    {"group": "Property", "key": "service_level", "label": "Service level"},
    {"group": "Landlord", "key": "landlord_full_name", "label": "Landlord full name"},
    {"group": "Landlord", "key": "landlord_email", "label": "Landlord email"},
    {"group": "Landlord", "key": "landlord_mobile", "label": "Landlord mobile"},
    {"group": "Landlord", "key": "landlord_address", "label": "Landlord address"},
    {"group": "Landlord", "key": "landlord_post_code", "label": "Landlord postcode"},
    {"group": "Landlord", "key": "landlord_bank_name", "label": "Bank name"},
    {"group": "Landlord", "key": "landlord_account_name", "label": "Account name"},
    {"group": "Landlord", "key": "landlord_sort_code", "label": "Sort code"},
    {"group": "Landlord", "key": "landlord_account_number", "label": "Account number"},
    {"group": "Tenant", "key": "tenant_full_name", "label": "Tenant full name"},
    {"group": "Tenant", "key": "tenant_email", "label": "Tenant email"},
    {"group": "Tenant", "key": "tenant_address", "label": "Tenant address"},
    {"group": "Tenant", "key": "tenancy_start_date", "label": "Tenancy start date"},
    {"group": "Tenant", "key": "tenancy_end_date", "label": "Tenancy end date"},
    {"group": "Tenant", "key": "tenancy_term", "label": "Tenancy term"},
    {"group": "Tenant", "key": "monthly_rent", "label": "Monthly rent"},
    {"group": "Tenant", "key": "deposit_amount", "label": "Deposit amount"},
    {"group": "Tenant", "key": "holding_deposit", "label": "Holding deposit"},
    {"group": "Meta",   "key": "today", "label": "Today's date"},
]
