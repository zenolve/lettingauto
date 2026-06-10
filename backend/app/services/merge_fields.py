"""Build the `{{merge_field}}` context for correspondence from Airtable records.

Every key here is sourced from a real field on Properties / Landlords / Tenant
(verified against the live schema). Templates use `{{key}}`; anything a
template needs that ISN'T here is left as a `[bracketed]` manual blank for the
agent to fill in the editor.

Tenant resolution: prefer the property's linked tenant (set on offer
acceptance). Before acceptance, fall back to the most recent offer's lead
tenant so offer-stage letters (TPL-05/06) still prepopulate.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.config import settings
from app.db import supabase_client as at

# Agent / brand details used across all correspondence. brand_name comes from
# settings; the rest are editable constants here (move to config if they need
# to vary per environment).
_AGENT_OFFICE_ADDRESS = "11 Palace Gate, Kensington, London W8 5LS"
_AGENT_PHONE = "020 7937 0000"
_AGENT_EMAIL = "lettings@palacegate.co.uk"


def _first(v: Any) -> str | None:
    return v[0] if isinstance(v, list) and v else None


def _resolve_tenant(pf: dict) -> dict:
    """The property's tenant, or the latest offer's lead tenant pre-acceptance."""
    tid = _first(pf.get("Tenant"))
    if not tid:
        latest: dict | None = None
        for oid in pf.get("Offers") or []:
            try:
                of = at.get(at.TableNames.OFFERS, oid).get("fields", {})
            except Exception:
                continue
            if latest is None or (of.get("Created At") or "") > (latest.get("Created At") or ""):
                latest = of
        if latest:
            tid = _first(latest.get("Tenants"))
    if tid:
        try:
            return at.get(at.TableNames.TENANTS, tid).get("fields", {})
        except Exception:
            return {}
    return {}


def build_merge_context(property_id: str) -> dict[str, Any]:
    prop = at.get(at.TableNames.PROPERTIES, property_id)
    pf = prop.get("fields", {})

    landlord: dict = {}
    if (lid := _first(pf.get("Landlords"))):
        landlord = at.get(at.TableNames.LANDLORDS, lid).get("fields", {})
    tenant = _resolve_tenant(pf)

    return {
        # --- brand / agent (static) ---
        "brand_name": getattr(settings, "brand_name", "Palace Gate"),
        "agent_office_address": _AGENT_OFFICE_ADDRESS,
        "agent_phone": _AGENT_PHONE,
        "agent_email": _AGENT_EMAIL,
        "today": date.today().strftime("%d %B %Y"),

        # --- property ---
        "property_address": pf.get("Address", ""),
        "property_post_code": pf.get("post_code", "") or pf.get("Post Code", ""),
        "property_type": pf.get("Property Type", ""),
        "tenancy_type": pf.get("Tenancy Type", "Common Law"),
        "service_level": pf.get("Service Level", ""),
        "annual_rent": pf.get("Annual Rent ", ""),
        "rent_frequency": pf.get("Rent Frequency", ""),
        "epc_rating": pf.get("EPC Rating ", ""),
        "gas_cert_expiry": pf.get("Gas Certificates Expiry", ""),
        "eicr_expiry": pf.get("EICR Expiry", ""),
        "tenancy_expiry_date": pf.get("Tenancy Expiry Date", ""),
        "checkin_date": pf.get("Checkin_Date", ""),
        "checkout_date": pf.get("Checkout_Date", ""),
        "inventory_clerk": pf.get("Inventory_Clerk", ""),
        "holding_deposit_deadline": pf.get("Holding_Deposit_Deadline", ""),
        "deposit_registration_date": pf.get("Deposit Registration Date", ""),
        "westminster_licence_number": pf.get("Westminster_Licence_Number", ""),
        "hmo_flag": "Yes" if pf.get("HMO_Flag") else "No",

        # --- landlord ---
        "landlord_full_name": landlord.get("Full Name", ""),
        "landlord_email": landlord.get("Email Address", ""),
        "landlord_mobile": landlord.get("Mobile Number", ""),
        "landlord_address": landlord.get("Full Address", ""),
        "landlord_post_code": landlord.get("Post Code", ""),
        "landlord_company_name": landlord.get("Company Name", ""),
        "landlord_director_name": landlord.get("Director Name", ""),
        "landlord_resident_status": landlord.get("UK_Resident_Status", ""),
        "landlord_nrl_number": landlord.get("NRL_Approval_Number", ""),
        "landlord_bank_name": landlord.get("Bank Name", ""),
        "landlord_account_name": landlord.get("Account Name", ""),
        "landlord_sort_code": landlord.get("Sort Code", ""),
        "landlord_account_number": landlord.get("Account Number", ""),
        "block_manager_name": landlord.get("Block Manager Name", ""),
        "block_manager_contact": landlord.get("Block Manager Contact", ""),

        # --- tenant / offer terms ---
        "tenant_full_name": tenant.get("Name", ""),
        "tenant_email": tenant.get("Tenant Email", ""),
        "tenant_address": tenant.get("Tenant Address", ""),
        "tenancy_start_date": tenant.get("Start Date", "") or pf.get("Tenancy Start Date", ""),
        "tenancy_end_date": tenant.get("End Date", "") or "Periodic",
        "tenancy_term": tenant.get("Tenancy Term", ""),
        "monthly_rent": tenant.get("Amount", ""),
        "deposit_amount": tenant.get("Deposit Amount", "") or pf.get("Deposit", ""),
        "holding_deposit": tenant.get("Holding_Deposit", ""),
        "rent_in_advance_months": tenant.get("Rent_In_Advance_Months", ""),
        "break_clause": tenant.get("Break Clause", ""),
        "guarantor_name": tenant.get("Guarantor_Name", ""),
        "guarantor_email": tenant.get("Guarantor_Email", ""),
        "guarantor_address": tenant.get("Gurantor Address", ""),  # spelling per live schema
        "referencing_status": tenant.get("Referencing_Status", ""),
        "referencing_ref": tenant.get("Referencing_Paragon_Ref", ""),
        "visa_expiry_date": tenant.get("Visa_Expiry_Date", ""),
    }


# Catalogue exposed to the frontend editor palette.
MERGE_FIELD_CATALOGUE: list[dict] = [
    {"group": "Agent", "key": "brand_name", "label": "Agency name"},
    {"group": "Agent", "key": "agent_office_address", "label": "Agency address"},
    {"group": "Agent", "key": "agent_phone", "label": "Agency phone"},
    {"group": "Agent", "key": "agent_email", "label": "Agency email"},
    {"group": "Agent", "key": "today", "label": "Today's date"},

    {"group": "Property", "key": "property_address", "label": "Property address"},
    {"group": "Property", "key": "property_post_code", "label": "Property postcode"},
    {"group": "Property", "key": "property_type", "label": "Property type"},
    {"group": "Property", "key": "tenancy_type", "label": "Tenancy type"},
    {"group": "Property", "key": "service_level", "label": "Service level"},
    {"group": "Property", "key": "annual_rent", "label": "Annual rent"},
    {"group": "Property", "key": "rent_frequency", "label": "Rent frequency"},
    {"group": "Property", "key": "epc_rating", "label": "EPC rating"},
    {"group": "Property", "key": "gas_cert_expiry", "label": "Gas cert expiry"},
    {"group": "Property", "key": "eicr_expiry", "label": "EICR expiry"},
    {"group": "Property", "key": "tenancy_expiry_date", "label": "Tenancy expiry date"},
    {"group": "Property", "key": "checkin_date", "label": "Check-in date"},
    {"group": "Property", "key": "checkout_date", "label": "Check-out date"},
    {"group": "Property", "key": "inventory_clerk", "label": "Inventory clerk"},
    {"group": "Property", "key": "holding_deposit_deadline", "label": "Holding-deposit deadline"},
    {"group": "Property", "key": "deposit_registration_date", "label": "Deposit registration date"},
    {"group": "Property", "key": "westminster_licence_number", "label": "Westminster licence no."},
    {"group": "Property", "key": "hmo_flag", "label": "HMO (Yes/No)"},

    {"group": "Landlord", "key": "landlord_full_name", "label": "Landlord full name"},
    {"group": "Landlord", "key": "landlord_email", "label": "Landlord email"},
    {"group": "Landlord", "key": "landlord_mobile", "label": "Landlord mobile"},
    {"group": "Landlord", "key": "landlord_address", "label": "Landlord address"},
    {"group": "Landlord", "key": "landlord_post_code", "label": "Landlord postcode"},
    {"group": "Landlord", "key": "landlord_company_name", "label": "Company name"},
    {"group": "Landlord", "key": "landlord_director_name", "label": "Director name"},
    {"group": "Landlord", "key": "landlord_resident_status", "label": "Residency status"},
    {"group": "Landlord", "key": "landlord_nrl_number", "label": "NRL approval number"},
    {"group": "Landlord", "key": "landlord_bank_name", "label": "Bank name"},
    {"group": "Landlord", "key": "landlord_account_name", "label": "Account name"},
    {"group": "Landlord", "key": "landlord_sort_code", "label": "Sort code"},
    {"group": "Landlord", "key": "landlord_account_number", "label": "Account number"},
    {"group": "Landlord", "key": "block_manager_name", "label": "Block manager name"},
    {"group": "Landlord", "key": "block_manager_contact", "label": "Block manager contact"},

    {"group": "Tenant", "key": "tenant_full_name", "label": "Tenant full name"},
    {"group": "Tenant", "key": "tenant_email", "label": "Tenant email"},
    {"group": "Tenant", "key": "tenant_address", "label": "Tenant address"},
    {"group": "Tenant", "key": "tenancy_start_date", "label": "Tenancy start date"},
    {"group": "Tenant", "key": "tenancy_end_date", "label": "Tenancy end date"},
    {"group": "Tenant", "key": "tenancy_term", "label": "Tenancy term"},
    {"group": "Tenant", "key": "monthly_rent", "label": "Rent amount"},
    {"group": "Tenant", "key": "deposit_amount", "label": "Deposit amount"},
    {"group": "Tenant", "key": "holding_deposit", "label": "Holding deposit"},
    {"group": "Tenant", "key": "rent_in_advance_months", "label": "Rent in advance (months)"},
    {"group": "Tenant", "key": "break_clause", "label": "Break clause"},
    {"group": "Tenant", "key": "guarantor_name", "label": "Guarantor name"},
    {"group": "Tenant", "key": "guarantor_email", "label": "Guarantor email"},
    {"group": "Tenant", "key": "guarantor_address", "label": "Guarantor address"},
    {"group": "Tenant", "key": "referencing_status", "label": "Referencing status"},
    {"group": "Tenant", "key": "referencing_ref", "label": "Paragon reference"},
    {"group": "Tenant", "key": "visa_expiry_date", "label": "Visa expiry date"},
]
