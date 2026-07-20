"""Pydantic models used by both internal-form routers and webhook handlers."""
from __future__ import annotations

import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


def _empty_to_none(v):
    """Treat empty strings as None.

    The React forms send unfilled optional fields as ``""`` rather than
    omitting them; without this coercion Pydantic rejects every empty
    Optional[EmailStr] / Optional[date] / Optional[float] field with a 422.
    Apply to every optional field that has a stricter inner type.
    """
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


# ---------------------------------------------------------------------------
# PG_01 — Property take-on (Agent Add Property)
# ---------------------------------------------------------------------------
class PropertyTakeonInput(BaseModel):
    """PG_01 Take-on input.

    `asking_rent_pcm` is named for backwards-compat but the rent's interpretation
    depends on `rent_frequency` — weekly rents × 52 vs. monthly × 12 for the
    APT classification (Housing Act 1988 £100k threshold).
    """

    address: str = Field(..., min_length=3)
    post_code: str
    landlord_full_name: str
    landlord_email: EmailStr
    send_admin_form: bool = True
    # Recipient for the onboarding form when send_admin_form is False. Defaults
    # to the logged-in agent's email (set server-side in the forms router) so it
    # survives into pay-first fulfillment; the agent may override it in the form.
    agent_email: Optional[EmailStr] = None
    asking_rent_pcm: Optional[float] = None   # value of one rent payment (per frequency)
    rent_frequency: Literal["Monthly", "Weekly"] = "Monthly"
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# PG_02 — Landlord admin form
# ---------------------------------------------------------------------------
YesNo = Literal["Yes", "No"]


class LandlordAdminInput(BaseModel):
    """PG_02 landlord admin form payload.

    Fields ending in ``_upload`` are absolute URLs returned by the file-upload
    endpoint ``POST /api/uploads/{property_id}/{bucket}?token=<form_token>``.
    The frontend uploads the file first, then submits this form with the
    returned URLs. (Tally storage links are no longer used.)
    """

    # block manager
    # (Property postcode was previously asked here but is already on the
    # Property record from PG_01 — removed in Wave A consolidation.)
    block_manager_name: Optional[str] = None
    block_manager_address: Optional[str] = None
    block_manager_postal_code: Optional[str] = None
    block_manager_contact: Optional[str] = None
    block_manager_email: Optional[EmailStr] = None

    # consents
    consent_sublet: Optional[YesNo] = None
    consent_mortgagor: Optional[YesNo] = None
    mortgage_consent_upload: Optional[str] = None  # URL

    # landlord identity
    landlord_full_name: str
    landlord_full_address: str
    landlord_post_code: str
    landlord_mobile: str
    landlord_email: EmailStr

    # residency / NRL
    residency: str
    has_tax_exempt_number: Optional[YesNo] = None
    nrl_approval_number: Optional[str] = None
    applying_for_nrl: Optional[YesNo] = None
    pg_manage_nrl: Optional[str] = None
    pg_collect_pay_tax: Optional[YesNo] = None
    appoint_solicitor_for_tax: Optional[YesNo] = None
    tax_agent_name: Optional[str] = None
    written_to_inland_revenue: Optional[YesNo] = None

    # bank
    bank_name: Optional[str] = None
    bank_address: Optional[str] = None
    sort_code: Optional[str] = None
    account_name: Optional[str] = None
    account_number: Optional[str] = None

    @field_validator("sort_code")
    @classmethod
    def _validate_sort_code(cls, v: Optional[str]) -> Optional[str]:
        """UK sort codes are exactly 6 digits. Normalise to NN-NN-NN."""
        if v is None or not str(v).strip():
            return None
        digits = re.sub(r"\D", "", str(v))
        if len(digits) != 6:
            raise ValueError("Sort code must be exactly 6 digits (e.g. 12-34-56)")
        return f"{digits[0:2]}-{digits[2:4]}-{digits[4:6]}"

    @field_validator("account_number")
    @classmethod
    def _validate_account_number(cls, v: Optional[str]) -> Optional[str]:
        """UK account numbers are exactly 8 digits."""
        if v is None or not str(v).strip():
            return None
        digits = re.sub(r"\D", "", str(v))
        if len(digits) != 8:
            raise ValueError("Account number must be exactly 8 digits")
        return digits

    # tax-agent (only when appoint_solicitor_for_tax = Yes — see conditional in form)
    tax_agent_address: Optional[str] = None
    tax_agent_contact: Optional[str] = None

    # listing
    has_photos: Optional[YesNo] = None
    auth_photos: Optional[YesNo] = None
    has_inventory: Optional[YesNo] = None
    auth_inventory: Optional[YesNo] = None

    # property characteristics
    property_type: Optional[str] = None  # House / Flat
    tenure: Optional[str] = None         # Leasehold / Freehold
    unexpired_term: Optional[str] = None
    annual_service_charge: Optional[float] = None
    ground_rent: Optional[float] = None
    head_lease_upload: Optional[str] = None
    freeholder_consent: Optional[YesNo] = None
    freeholder_consent_upload: Optional[str] = None
    who_manages_property: Optional[str] = None
    third_party_manager: Optional[str] = None
    insurance_in_place: Optional[YesNo] = None
    insurance_provider: Optional[str] = None
    insurance_policy_number: Optional[str] = None
    insurance_cert_upload: Optional[str] = None

    # utilities info (free text — matched 1:1 to the Tally textarea labels)
    telephone_provider_account: Optional[str] = None  # "Telephone Number, Provider & Account Number"
    gas_provider_meter: Optional[str] = None
    electricity_provider_meter: Optional[str] = None
    water_provider: Optional[str] = None
    cable_tv_details: Optional[str] = None
    council_tax_borough: Optional[str] = None
    gas_tap_location: Optional[str] = None
    water_stopcock_location: Optional[str] = None
    electricity_main_switch: Optional[str] = None
    refuse_collection_day: Optional[str] = None

    # certificates — Tally marks the "Do you have…" questions as required and
    # legally they should be; matched on 2026-05-16 to bring our internal form
    # in line.
    has_gas_cert: YesNo
    arrange_gas_cert: Optional[YesNo] = None
    gas_cert_expiry: Optional[date] = None
    gas_cert_upload: Optional[str] = None

    has_epc: YesNo
    arrange_epc: Optional[YesNo] = None
    epc_rating: Optional[str] = None
    epc_upload: Optional[str] = None

    has_eicr: YesNo
    arrange_eicr: Optional[YesNo] = None
    eicr_expiry: Optional[date] = None
    eicr_upload: Optional[str] = None

    smoke_detectors_fitted: YesNo
    furniture_fire_regs: Optional[YesNo] = None
    supply_keys: Optional[YesNo] = None
    alternative_access: Optional[str] = None

    # Coerce "" → None on every optional non-string field so the React form
    # can submit blanks without a 422. Required str fields (landlord_email
    # etc.) are unaffected.
    @field_validator(
        "block_manager_email",
        "gas_cert_expiry", "eicr_expiry",
        "annual_service_charge", "ground_rent",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v):
        return _empty_to_none(v)


# ---------------------------------------------------------------------------
# PG_02b — Landlord verification
# ---------------------------------------------------------------------------
class LandlordVerificationInput(BaseModel):
    """PG_02b landlord verification form payload.

    Fields ending in ``_upload`` (and ``visa_snapshot``,
    ``certificate_of_incorporation``) are absolute URLs returned by the
    file-upload endpoint — see ``LandlordAdminInput`` for the same convention.
    """

    individual_or_company: str  # Individual / Company
    # Residency is no longer asked on this form (Wave B consolidation) — PG_02
    # already captured it and it's stored on the Landlord as UK_Resident_Status.
    # Kept optional so the legacy Tally webhook shim can still pass it and the
    # handler can fall back to it if the landlord record somehow lacks a status.
    residency: Optional[str] = None

    id_document_type: Optional[str] = None
    id_document_upload: Optional[str] = None
    visa_snapshot: Optional[str] = None

    address_doc_type: Optional[str] = None
    address_doc_upload: Optional[str] = None
    ownership_doc_upload: Optional[str] = None

    # company-only
    company_name: Optional[str] = None
    company_reg_number: Optional[str] = None
    company_reg_address: Optional[str] = None
    certificate_of_incorporation: Optional[str] = None
    director_name: Optional[str] = None
    bank_statements_upload: Optional[str] = None

    source_of_funds: Optional[str] = None
    purchase_explanation: Optional[str] = None

    # No EmailStr / date / float fields on this model, but coerce defensively
    # so the React form can submit blanks without 422-ing later.
    @field_validator("*", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        return _empty_to_none(v) if v == "" else v


# ---------------------------------------------------------------------------
# PG_03 — Offer
# ---------------------------------------------------------------------------
RTRCheckType = Literal["Manual", "IDSP", "Share Code", "Paragon"]


class CoTenantInput(BaseModel):
    """One additional tenant on a multi-tenant tenancy.

    The lead tenant lives on ``OfferInput`` directly. Add one of these per
    extra named tenant or occupier (HMO households often have 3+ tenants;
    Housing Act 2004 may require an HMO licence at that point).
    """

    full_name: str
    email: EmailStr
    address: Optional[str] = None
    is_student: bool = False
    visa_expiry_date: Optional[date] = None
    rtr_check_type: Optional[RTRCheckType] = None
    rtr_check_date: Optional[date] = None
    rtr_doc_reference: Optional[str] = None


class OfferInput(BaseModel):
    """PG_03 offer input.

    Step 35–38 (master doc): tenant full details + Right-to-Rent docs.
    Step 46 (master doc): Paragon referencing — the system auto-instructs
    Paragon when ``instruct_paragon`` is true and stores the returned
    reference number against the tenant record.
    """

    tenant_full_name: str
    tenant_email: EmailStr
    tenant_address: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    tenancy_term: Optional[str] = None
    monthly_rent: float
    rent_frequency: Literal["Monthly", "Weekly"] = "Monthly"
    deposit_amount: float
    # Optional: a holding deposit is not always taken (UAT feedback). None =
    # "none taken"; the APT one-week cap check only runs when a value is set.
    holding_deposit: Optional[float] = None
    rent_in_advance_months: int = 0
    # Break clause is a currency field in Airtable (Tenant.Break Clause) —
    # interpreted as the break-clause activation fee in £. The form posts a
    # numeric value or blank.
    break_clause: Optional[float] = None
    renewal_terms: Optional[str] = None
    special_conditions: Optional[str] = None
    number_of_occupants: int = 1
    guarantor_name: Optional[str] = None
    guarantor_address: Optional[str] = None
    guarantor_email: Optional[EmailStr] = None
    is_student: bool = False

    # --- Right to Rent (steps 35–38) -----------------------------------
    # All four are absolute URLs returned by the upload endpoint; the agent
    # uploads each through /api/uploads/agent/{property_id}/{bucket}.
    tenant_passport_upload: Optional[str] = None
    tenant_visa_upload: Optional[str] = None       # only if non-UK / time-limited
    tenant_utility_bill_upload: Optional[str] = None
    rtr_check_type: Optional[RTRCheckType] = None
    rtr_check_date: Optional[date] = None
    rtr_doc_reference: Optional[str] = None
    visa_expiry_date: Optional[date] = None        # triggers RTR follow-up diary

    # --- Paragon referencing (step 46) ---------------------------------
    instruct_paragon: bool = True

    # --- Equality Act 2010 confirmation --------------------------------
    # Agent confirms they have not discriminated against any prospective
    # tenant. Required for APT compliance; recorded on Properties so it
    # appears in the audit trail with a date.
    anti_discrimination_confirmed: bool = False

    # --- Additional tenants (step 26 multi-tenant) ---------------------
    co_tenants: list[CoTenantInput] = Field(default_factory=list)

    @field_validator(
        "tenant_address", "tenancy_term", "break_clause", "renewal_terms",
        "special_conditions", "guarantor_name", "guarantor_address",
        "guarantor_email", "end_date",
        "tenant_passport_upload", "tenant_visa_upload", "tenant_utility_bill_upload",
        "rtr_check_type", "rtr_doc_reference", "rtr_check_date", "visa_expiry_date",
        "monthly_rent", "deposit_amount", "holding_deposit",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v):
        return _empty_to_none(v)
