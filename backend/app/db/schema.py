"""Schema registry for the Supabase (Postgres) backend.

Maps the legacy Airtable field names — which the rest of the codebase still
uses, trailing-space oddities included ("Annual Rent ", "EPC Rating ",
"Gurantor Address") — onto the relational schema created by
``supabase/migrations/001_init.sql``.

Three kinds of field per table:

* **columns** — scalar values stored on the table itself.
* **links** — Airtable's symmetric linked-record fields. Each link pair is
  one junction table; both sides declare the same junction with near/far
  swapped, so reads and writes work from either direction (exactly like
  Airtable's automatic reverse links).
* **computed** — Airtable lookup fields (e.g. ``Properties.Stage_Order``),
  recomputed at read time via a SQL subquery.

The adapter (``supabase_client.py``) is generic over this registry: adding a
field here (and a column in a migration) is all that's needed to expose it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Value types understood by the adapter (read conversion + write coercion).
# text | bool | number | int | date | timestamptz | json | uuid
@dataclass(frozen=True)
class Col:
    name: str
    type: str = "text"


@dataclass(frozen=True)
class Link:
    """One side of a symmetric link.

    ``junction``: junction table name.
    ``near``:     junction column holding THIS table's row id.
    ``far``:      junction column holding the far table's row id.
    ``far_table``: logical name (TableNames value) of the far table — used for
                   cache invalidation, since editing a link changes what reads
                   of *both* tables return.
    """
    junction: str
    near: str
    far: str
    far_table: str


@dataclass(frozen=True)
class TableSchema:
    sql_table: str
    columns: dict[str, Col]
    links: dict[str, Link] = field(default_factory=dict)
    computed: dict[str, str] = field(default_factory=dict)  # name -> SELECT subquery ({alias} = base row alias)


# Multi-tenancy: every operational table carries an ``agency_id`` column the
# adapter scopes automatically (see supabase_client.set_agency_scope). It is
# exposed as a plain field named "agency_id" so system paths (webhooks,
# billing) can also filter on it explicitly.
_AGENCY = {"agency_id": Col("agency_id", "uuid")}


SCHEMAS: dict[str, TableSchema] = {
    # ------------------------------------------------------------------ stages
    "stages": TableSchema(
        sql_table="stages",
        columns={
            "Stage Name": Col("stage_name"),
            "Order": Col("stage_order", "int"),
            "Stage agent": Col("stage_agent", "json"),
        },
    ),

    # ---------------------------------------------------------------- agencies
    "agencies": TableSchema(
        sql_table="agencies",
        columns={
            "name": Col("name"),
            "slug": Col("slug"),
            "email": Col("email"),
            "phone": Col("phone"),
            "office_address": Col("office_address"),
            "website": Col("website"),
            "logo_url": Col("logo_url"),
            "brand_navy": Col("brand_navy"),
            "brand_gold": Col("brand_gold"),
            "onboarding_completed": Col("onboarding_completed", "bool"),
            "stripe_customer_id": Col("stripe_customer_id"),
            "stripe_subscription_id": Col("stripe_subscription_id"),
            "subscription_status": Col("subscription_status"),
            "payment_method_on_file": Col("payment_method_on_file", "bool"),
            "billing_email": Col("billing_email"),
        },
    ),

    # ------------------------------------------------------------ agency_users
    "agency_users": TableSchema(
        sql_table="agency_users",
        columns={
            "agency_id": Col("agency_id", "uuid"),
            "user_id": Col("user_id", "uuid"),
            "email": Col("email"),
            "full_name": Col("full_name"),
            "role": Col("role"),
        },
    ),

    # -------------------------------------------------------------- properties
    "properties": TableSchema(
        sql_table="properties",
        columns={
            **_AGENCY,
            "Address": Col("address"),
            "post_code": Col("post_code"),
            "Type": Col("type"),
            "Tenancy Type": Col("tenancy_type"),
            "Rent Frequency": Col("rent_frequency"),
            "Annual Rent ": Col("annual_rent", "number"),     # trailing space is real
            "landlord_email": Col("landlord_email"),
            "Service Level": Col("service_level"),
            "Property Type": Col("property_type"),
            "Gate Status": Col("gate_status"),
            "Gate Block Reason": Col("gate_block_reason"),
            "Stage changed at": Col("stage_changed_at", "date"),
            "EPC Rating ": Col("epc_rating"),                 # trailing space is real
            "Gas Certificates Expiry": Col("gas_cert_expiry", "date"),
            "EICR Expiry": Col("eicr_expiry", "date"),
            "Gas_Cert_Status": Col("gas_cert_status"),
            "EPC_Status": Col("epc_status"),
            "EICR_Status": Col("eicr_status"),
            "smoke_detectors_fitted": Col("smoke_detectors_fitted", "bool"),
            "mortgage_consent_url": Col("mortgage_consent_url"),
            "head_lease_url": Col("head_lease_url"),
            "freeholder_consent_url": Col("freeholder_consent_url"),
            "Insurance_provider": Col("insurance_provider"),
            "Insurance_policy_number": Col("insurance_policy_number"),
            "Insurance_certificate_url": Col("insurance_certificate_url"),
            "TC_Signed": Col("tc_signed", "bool"),
            "TA_LL_Signed": Col("ta_ll_signed", "bool"),
            "TA_TT_Signed": Col("ta_tt_signed", "bool"),
            "LL_Offer_Accepted": Col("ll_offer_accepted", "bool"),
            "Anti_Discrimination_Confirmed": Col("anti_discrimination_confirmed", "bool"),
            "Anti_Discrimination_Confirmed_Date": Col("anti_discrimination_confirmed_date", "date"),
            "HMO_Flag": Col("hmo_flag", "bool"),
            "HMO_Licence_Confirmed": Col("hmo_licence_confirmed", "bool"),
            "Holding_Deposit_Deadline": Col("holding_deposit_deadline", "date"),
            "TDS Cert On File": Col("tds_cert_on_file", "bool"),
            "Deposit Registered": Col("deposit_registered", "bool"),
            "Deposit Registration Date": Col("deposit_registration_date", "date"),
            "Deposit": Col("deposit", "number"),
            "funds_cleared": Col("funds_cleared", "bool"),
            "Works_Signed_Off": Col("works_signed_off", "bool"),
            "How_To_Rent_Served": Col("how_to_rent_served", "bool"),
            "Gas_Cert_Served": Col("gas_cert_served", "bool"),
            "EPC_Served": Col("epc_served", "bool"),
            "EICR_Served": Col("eicr_served", "bool"),
            "TDS_Info_Served": Col("tds_info_served", "bool"),
            "RRA_Sheet_Served": Col("rra_sheet_served", "bool"),
            "RRA_sheet_served_date": Col("rra_sheet_served_date", "date"),
            "Tenancy Start Date": Col("tenancy_start_date", "date"),
            "Tenancy Expiry Date": Col("tenancy_expiry_date", "date"),
            "Checkin_Date": Col("checkin_date", "date"),
            "Checkout_Date": Col("checkout_date", "date"),
            "Inventory_Clerk": Col("inventory_clerk"),
            "Westminster_Licence_Number": Col("westminster_licence_number"),
        },
        links={
            "Stage": Link("property_stage", "property_id", "stage_id", "stages"),
            "Landlords": Link("property_landlords", "property_id", "landlord_id", "landlords"),
            "Tenant": Link("property_tenants", "property_id", "tenant_id", "tenants"),
            "Tenancy Checklist": Link("property_checklist_items", "property_id", "checklist_id", "checklist"),
            # Reverse sides of links owned by other tables (Airtable auto-reverse):
            "Offers": Link("offer_properties", "property_id", "offer_id", "offers"),
            "Diary": Link("diary_properties", "property_id", "diary_id", "diary"),
            "Financials": Link("financials_properties", "property_id", "financial_id", "financials"),
            "Submissions": Link("submissions_properties", "property_id", "submission_id", "submissions"),
            "Gate_Log": Link("gate_log_properties", "property_id", "gate_log_id", "gate_log"),
            "Compliance": Link("compliance_properties", "property_id", "compliance_id", "compliance"),
            "Sent_Documents": Link("sent_documents_properties", "property_id", "sent_document_id", "sent_documents"),
            "Checklist": Link("checklist_properties", "property_id", "checklist_id", "checklist"),
        },
        computed={
            # Airtable lookup: the linked Stage's Order.
            "Stage_Order": (
                "(select s.stage_order from property_stage ps "
                "join stages s on s.id = ps.stage_id "
                "where ps.property_id = {alias}.id "
                "order by ps.position, ps.created_at limit 1)"
            ),
        },
    ),

    # --------------------------------------------------------------- landlords
    "landlords": TableSchema(
        sql_table="landlords",
        columns={
            **_AGENCY,
            "Full Name": Col("full_name"),
            "Email Address": Col("email_address"),
            "Mobile Number": Col("mobile_number"),
            "Full Address": Col("full_address"),
            "Post Code": Col("post_code"),
            "Verification Status": Col("verification_status"),
            "TA_Signed": Col("ta_signed", "bool"),
            "TC_Signed": Col("tc_signed", "bool"),
            "Primary_For_Disbursement": Col("primary_for_disbursement", "bool"),
            "Ownership_Share_Percent": Col("ownership_share_percent", "number"),
            "UK_Resident_Status": Col("uk_resident_status"),
            "NRL_Withholding_Active": Col("nrl_withholding_active", "bool"),
            "NRL_Approval_Number": Col("nrl_approval_number"),
            "NRL_Tax_Cert_Diary_Set": Col("nrl_tax_cert_diary_set", "bool"),
            "Bank Name": Col("bank_name"),
            "Sort Code": Col("sort_code"),
            "Account Name": Col("account_name"),
            "Account Number": Col("account_number"),
            "Block Manager Name": Col("block_manager_name"),
            "Block Manager Address": Col("block_manager_address"),
            "Block Manager Postal Code": Col("block_manager_postal_code"),
            "Block Manager Contact": Col("block_manager_contact"),
            "Block Manager Email": Col("block_manager_email"),
            "Individual or Company": Col("individual_or_company"),
            "ID Document Type": Col("id_document_type"),
            "ID Document URL": Col("id_document_url"),
            "Visa Snapshot URL": Col("visa_snapshot_url"),
            "Address Doc Type": Col("address_doc_type"),
            "Address Document URL": Col("address_document_url"),
            "Ownership Document URL": Col("ownership_document_url"),
            "Company Name": Col("company_name"),
            "Company Reg Number": Col("company_reg_number"),
            "Company Reg Address": Col("company_reg_address"),
            "Director Name": Col("director_name"),
            "Incorporation Doc URL": Col("incorporation_doc_url"),
            "Bank Statements URL": Col("bank_statements_url"),
            "Source of Funds": Col("source_of_funds"),
            "Purchase Explanation": Col("purchase_explanation"),
            "ID_Name_Match": Col("id_name_match"),
            "AML_Check_Date": Col("aml_check_date", "date"),
            "AML_Checked_By": Col("aml_checked_by"),
        },
        links={
            "Properties": Link("property_landlords", "landlord_id", "property_id", "properties"),
        },
    ),

    # ----------------------------------------------------------------- tenants
    "tenants": TableSchema(
        sql_table="tenants",
        columns={
            **_AGENCY,
            "Name": Col("name"),
            "Tenant Email": Col("tenant_email"),
            "Tenant Address": Col("tenant_address"),
            "Start Date": Col("start_date", "date"),
            "End Date": Col("end_date", "date"),
            "Tenancy Term": Col("tenancy_term"),
            "Amount": Col("amount", "number"),
            "Rent_Frequency": Col("rent_frequency"),
            "Deposit Amount": Col("deposit_amount", "number"),
            "Holding_Deposit": Col("holding_deposit", "number"),
            "Rent_In_Advance_Months": Col("rent_in_advance_months", "int"),
            "Break Clause": Col("break_clause", "number"),
            "Renew": Col("renew"),
            "Special Condition": Col("special_condition"),
            "Guarantor_Name": Col("guarantor_name"),
            "Gurantor Address": Col("guarantor_address"),     # (sic) live-schema spelling
            "Guarantor_Email": Col("guarantor_email"),
            "Is_Student": Col("is_student", "bool"),
            "Referencing_Status": Col("referencing_status"),
            "Referencing_Recorded": Col("referencing_recorded", "bool"),
            "Referencing_Paragon_Ref": Col("referencing_paragon_ref"),
            "Landlord_Approval_Received": Col("landlord_approval_received", "bool"),
            "TA_Signed": Col("ta_signed", "bool"),
            "RTR_Check_Type": Col("rtr_check_type"),
            "RTR_Check_Date": Col("rtr_check_date", "date"),
            "RTR_Doc_Reference": Col("rtr_doc_reference"),
            "Visa_Expiry_Date": Col("visa_expiry_date", "date"),
        },
        links={
            # NOT the reverse of Properties.Tenant — a deliberately separate
            # relationship (Gap 5): tenants point at the property from offer
            # creation; the property points back only when an offer is accepted.
            "Property Id": Link("tenant_property_id", "tenant_id", "property_id", "properties"),
            "Offers": Link("offer_tenants", "tenant_id", "offer_id", "offers"),
            "Compliance": Link("compliance_tenants", "tenant_id", "compliance_id", "compliance"),
        },
    ),

    # ------------------------------------------------------------------ offers
    "offers": TableSchema(
        sql_table="offers",
        columns={
            **_AGENCY,
            "Name": Col("name"),
            "Status": Col("status"),
            "Offered Rent": Col("offered_rent", "number"),
            "Rent Frequency": Col("rent_frequency"),
            "Deposit": Col("deposit", "number"),
            "Holding Deposit": Col("holding_deposit", "number"),
            "Start Date": Col("start_date", "date"),
            "End Date": Col("end_date", "date"),
            "Tenancy Term": Col("tenancy_term"),
            "Holding Deposit Deadline": Col("holding_deposit_deadline", "date"),
            "DocuSign Envelope ID": Col("docusign_envelope_id"),
            "Created At": Col("created_on", "date"),
            "Closed At": Col("closed_on", "date"),
            "Close Reason": Col("close_reason"),
            "Created By": Col("created_by"),
            "Notes": Col("notes"),
        },
        links={
            "Property": Link("offer_properties", "offer_id", "property_id", "properties"),
            "Tenants": Link("offer_tenants", "offer_id", "tenant_id", "tenants"),
        },
    ),

    # ------------------------------------------------------------------- diary
    "diary": TableSchema(
        sql_table="diary",
        columns={
            **_AGENCY,
            "Diary_Type": Col("diary_type"),
            "Diary Date": Col("diary_date", "date"),
            "Alert_Date": Col("alert_date", "date"),
            "Alert_Message": Col("alert_message"),
            "Assigned_To": Col("assigned_to"),
            "Fired": Col("fired", "bool"),
            "Fired_Date": Col("fired_date", "date"),
        },
        links={
            "Property": Link("diary_properties", "diary_id", "property_id", "properties"),
        },
    ),

    # -------------------------------------------------------------- financials
    "financials": TableSchema(
        sql_table="financials",
        columns={
            **_AGENCY,
            "Commission_Rate": Col("commission_rate", "number"),
            "Disbursement_Status": Col("disbursement_status"),
        },
        links={
            "Property": Link("financials_properties", "financial_id", "property_id", "properties"),
        },
    ),

    # --------------------------------------------------------------- checklist
    "checklist": TableSchema(
        sql_table="checklist",
        columns={
            **_AGENCY,
            "Name": Col("name"),
            "Priority": Col("priority"),
            "applies_to": Col("applies_to", "json"),
            "Is_Template": Col("is_template", "bool"),
            "is_gate_item": Col("is_gate_item", "bool"),
            "Status": Col("status"),
        },
        links={
            "Property": Link("checklist_properties", "checklist_id", "property_id", "properties"),
            "Properties": Link("property_checklist_items", "checklist_id", "property_id", "properties"),
        },
    ),

    # ------------------------------------------------------------- submissions
    "submissions": TableSchema(
        sql_table="submissions",
        columns={
            **_AGENCY,
            "Form Name": Col("form_name"),
            "Submitted Date": Col("submitted_date", "date"),
            "JSON Data": Col("json_data"),
        },
        links={
            "Property": Link("submissions_properties", "submission_id", "property_id", "properties"),
        },
    ),

    # ---------------------------------------------------------------- gate_log
    "gate_log": TableSchema(
        sql_table="gate_log",
        columns={
            **_AGENCY,
            "Attempted_At": Col("attempted_at", "timestamptz"),
            "From_Stage": Col("from_stage"),
            "To_Stage": Col("to_stage"),
            "Result": Col("result"),
            "Block_Reason": Col("block_reason"),
            "Gate Warnings": Col("gate_warnings"),
            "Gate Actions": Col("gate_actions"),
            "Gate Warnings Updated": Col("gate_warnings_updated", "date"),
            "Gate Warnings Source": Col("gate_warnings_source"),
            "Gate Warnings Dismissed": Col("gate_warnings_dismissed", "bool"),
            "Resolved_By": Col("resolved_by"),
            "Resolved_At": Col("resolved_at", "timestamptz"),
        },
        links={
            "Property": Link("gate_log_properties", "gate_log_id", "property_id", "properties"),
        },
    ),

    # -------------------------------------------------------------- compliance
    "compliance": TableSchema(
        sql_table="compliance",
        columns={
            **_AGENCY,
            "Document_Type": Col("document_type"),
            "Served_Date": Col("served_date", "date"),
            "Served_To": Col("served_to"),
            "Served_As": Col("served_as"),
            "File_URL": Col("file_url"),
            "Confirmed_Sent": Col("confirmed_sent", "bool"),
        },
        links={
            "Property": Link("compliance_properties", "compliance_id", "property_id", "properties"),
            "Tenant": Link("compliance_tenants", "compliance_id", "tenant_id", "tenants"),
        },
    ),

    # ---------------------------------------------------------- sent_documents
    "sent_documents": TableSchema(
        sql_table="sent_documents",
        columns={
            **_AGENCY,
            "Name": Col("name"),
            "Doc ID": Col("doc_id"),
            "Doc Name": Col("doc_name"),
            "Stage": Col("stage", "int"),
            "Channel": Col("channel"),
            "Recipients": Col("recipients"),
            "Sent Date": Col("sent_date", "date"),
            "Sent By": Col("sent_by"),
            "PDF URL": Col("pdf_url"),
            "Envelope ID": Col("envelope_id"),
            "Status": Col("status"),
            "Completed Date": Col("completed_date", "date"),
        },
        links={
            "Property": Link("sent_documents_properties", "sent_document_id", "property_id", "properties"),
        },
    ),

    # ---------------------------------------------------------------- payments
    # New table for the Stripe integration — no Airtable ancestor, so field
    # names are already snake_case.
    "payments": TableSchema(
        sql_table="payments",
        columns={
            **_AGENCY,
            "property_id": Col("property_id", "uuid"),
            "tenant_id": Col("tenant_id", "uuid"),
            "offer_id": Col("offer_id", "uuid"),
            "payment_type": Col("payment_type"),
            "amount": Col("amount", "number"),
            "currency": Col("currency"),
            "status": Col("status"),
            "description": Col("description"),
            "stripe_checkout_session_id": Col("stripe_checkout_session_id"),
            "stripe_payment_intent_id": Col("stripe_payment_intent_id"),
            "stripe_customer_id": Col("stripe_customer_id"),
            "stripe_invoice_id": Col("stripe_invoice_id"),
            "metadata": Col("metadata", "json"),
        },
    ),
}
