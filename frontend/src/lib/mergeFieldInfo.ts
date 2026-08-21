/**
 * Front-end reference catalogue for merge attributes: group, key, label, a
 * realistic SAMPLE value, and a plain-language DESCRIPTION. Used by editors that
 * have no property context (the base-template editor) to show what each token is
 * and what it produces. Keep the keys aligned with
 * backend/app/services/merge_fields.py (MERGE_FIELD_CATALOGUE / build_merge_context).
 */
export type MergeFieldInfo = {
  group: string;
  key: string;
  label: string;
  sample: string;
  description: string;
};

export const MERGE_FIELDS: MergeFieldInfo[] = [
  // --- Agent / agency ---
  { group: "Agent", key: "agency_name", label: "Agency name", sample: "Palace Gate", description: "Your agency's name, from your branding settings." },
  { group: "Agent", key: "brand_name", label: "Agency name (alias)", sample: "Palace Gate", description: "Same as the agency name — an alias kept for older templates." },
  { group: "Agent", key: "agent_office_address", label: "Agency address", sample: "1 High Street, London W8 5LS", description: "Your agency's office address." },
  { group: "Agent", key: "agent_phone", label: "Agency phone", sample: "020 7581 1631", description: "Your agency's phone number." },
  { group: "Agent", key: "agent_email", label: "Agency email", sample: "management@palacegate.com", description: "Your agency's contact email." },
  { group: "Agent", key: "today", label: "Today's date", sample: "09 August 2026", description: "Today's date, e.g. 09 August 2026." },

  // --- Property ---
  { group: "Property", key: "property_address", label: "Property address", sample: "12 Bramley Road, Flat 2", description: "The property's street address." },
  { group: "Property", key: "property_post_code", label: "Property postcode", sample: "W10 6SZ", description: "The property's postcode." },
  { group: "Property", key: "property_type", label: "Property type", sample: "Flat", description: "Type of property (flat, house, etc.)." },
  { group: "Property", key: "tenancy_type", label: "Tenancy type", sample: "APT", description: "APT (assured periodic) or Common Law." },
  { group: "Property", key: "service_level", label: "Service level", sample: "Full Management", description: "Management level — Full Management, Rent Collection or Let Only." },
  { group: "Property", key: "annual_rent", label: "Annual rent", sample: "£18,000.00", description: "Annual rent, formatted with a £." },
  { group: "Property", key: "rent_frequency", label: "Rent frequency", sample: "Monthly", description: "How often rent is paid (Monthly / Weekly)." },
  { group: "Property", key: "epc_rating", label: "EPC rating", sample: "C", description: "The property's EPC energy rating (A–G)." },
  { group: "Property", key: "gas_cert_expiry", label: "Gas cert expiry", sample: "12 Feb 2027", description: "Expiry date of the gas safety certificate." },
  { group: "Property", key: "eicr_expiry", label: "EICR expiry", sample: "03 Mar 2029", description: "Expiry date of the electrical (EICR) report." },
  { group: "Property", key: "tenancy_expiry_date", label: "Tenancy expiry date", sample: "Periodic", description: "The tenancy end/expiry date on the property record." },
  { group: "Property", key: "checkin_date", label: "Check-in date", sample: "01 Sep 2026", description: "Move-in / check-in date." },
  { group: "Property", key: "checkout_date", label: "Check-out date", sample: "31 Aug 2027", description: "Move-out / check-out date." },
  { group: "Property", key: "inventory_clerk", label: "Inventory clerk", sample: "No1 Inventories", description: "Name of the inventory clerk." },
  { group: "Property", key: "holding_deposit_deadline", label: "Holding-deposit deadline", sample: "24 Aug 2026", description: "Deadline to decide on the holding deposit (Tenant Fees Act — 15 days)." },
  { group: "Property", key: "deposit_registration_date", label: "Deposit registration date", sample: "05 Sep 2026", description: "Date the deposit was registered with the scheme." },
  { group: "Property", key: "westminster_licence_number", label: "Westminster licence no.", sample: "WCC/HMO/12345", description: "Selective/additional licence number (Westminster)." },
  { group: "Property", key: "hmo_flag", label: "HMO (Yes/No)", sample: "No", description: "Whether the property is flagged as an HMO (Yes/No)." },

  // --- Landlord ---
  { group: "Landlord", key: "landlord_full_name", label: "Landlord full name", sample: "Jane Smith", description: "The landlord's full name." },
  { group: "Landlord", key: "landlord_email", label: "Landlord email", sample: "jane.smith@example.com", description: "The landlord's email address." },
  { group: "Landlord", key: "landlord_mobile", label: "Landlord mobile", sample: "07700 900123", description: "The landlord's mobile number." },
  { group: "Landlord", key: "landlord_address", label: "Landlord address", sample: "5 Oak Avenue, Reading RG1 1AA", description: "The landlord's full address." },
  { group: "Landlord", key: "landlord_post_code", label: "Landlord postcode", sample: "RG1 1AA", description: "The landlord's postcode." },
  { group: "Landlord", key: "landlord_company_name", label: "Company name", sample: "Smith Holdings Ltd", description: "Company name, if the landlord is a company." },
  { group: "Landlord", key: "landlord_director_name", label: "Director name", sample: "Jane Smith", description: "Director's name, for company landlords." },
  { group: "Landlord", key: "landlord_resident_status", label: "Residency status", sample: "Resident", description: "Whether the landlord is UK-resident or non-resident." },
  { group: "Landlord", key: "landlord_nrl_number", label: "NRL approval number", sample: "NA123456", description: "HMRC Non-Resident Landlord approval number." },
  { group: "Landlord", key: "landlord_bank_name", label: "Bank name", sample: "Barclays", description: "Landlord's bank name (for rent disbursement)." },
  { group: "Landlord", key: "landlord_account_name", label: "Account name", sample: "J Smith", description: "Name on the landlord's bank account." },
  { group: "Landlord", key: "landlord_sort_code", label: "Sort code", sample: "12-34-56", description: "Landlord's bank sort code." },
  { group: "Landlord", key: "landlord_account_number", label: "Account number", sample: "12345678", description: "Landlord's bank account number." },
  { group: "Landlord", key: "block_manager_name", label: "Block manager name", sample: "Prime Block Management", description: "Name of the building's block / managing agent." },
  { group: "Landlord", key: "block_manager_contact", label: "Block manager contact", sample: "020 7000 0000", description: "Contact details for the block manager." },

  // --- Tenant / offer terms ---
  { group: "Tenant", key: "tenant_full_name", label: "Tenant full name", sample: "Tom Jones", description: "The lead tenant's full name." },
  { group: "Tenant", key: "tenant_email", label: "Tenant email", sample: "tom.jones@example.com", description: "The tenant's email address." },
  { group: "Tenant", key: "tenant_address", label: "Tenant address", sample: "88 Elm Road, London N1 2BB", description: "The tenant's current address." },
  { group: "Tenant", key: "tenancy_start_date", label: "Tenancy start date", sample: "01 Sep 2026", description: "The tenancy start date." },
  { group: "Tenant", key: "tenancy_end_date", label: "Tenancy end date", sample: "Periodic", description: "The tenancy end date, or 'Periodic' if there isn't one." },
  { group: "Tenant", key: "tenancy_term", label: "Tenancy term", sample: "12 months", description: "Length of the tenancy term." },
  { group: "Tenant", key: "monthly_rent", label: "Rent amount", sample: "£1,500.00", description: "The agreed rent amount, formatted with a £." },
  { group: "Tenant", key: "deposit_amount", label: "Deposit amount", sample: "£1,730.00", description: "The security deposit amount, formatted with a £." },
  { group: "Tenant", key: "holding_deposit", label: "Holding deposit", sample: "£346.00", description: "The holding deposit amount, formatted with a £." },
  { group: "Tenant", key: "rent_in_advance_months", label: "Rent in advance (months)", sample: "1", description: "Months of rent paid in advance." },
  { group: "Tenant", key: "break_clause", label: "Break clause", sample: "6 months", description: "Break-clause fee / terms, if any." },
  { group: "Tenant", key: "special_conditions", label: "Special conditions", sample: "Professional clean at check-out", description: "Any special conditions agreed on the offer." },
  { group: "Tenant", key: "guarantor_name", label: "Guarantor name", sample: "Robert Jones", description: "The guarantor's name, if there is one." },
  { group: "Tenant", key: "guarantor_email", label: "Guarantor email", sample: "robert.jones@example.com", description: "The guarantor's email." },
  { group: "Tenant", key: "guarantor_address", label: "Guarantor address", sample: "10 Pine Lane, Bristol BS1 3CC", description: "The guarantor's address." },
  { group: "Tenant", key: "referencing_status", label: "Referencing status", sample: "Pass", description: "Outcome of tenant referencing (Pass / Conditional / Fail)." },
  { group: "Tenant", key: "referencing_ref", label: "Paragon reference", sample: "PARA-123456", description: "The referencing provider (Paragon) reference." },
  { group: "Tenant", key: "visa_expiry_date", label: "Visa expiry date", sample: "14 Jun 2028", description: "Expiry date of the tenant's visa / right to rent." },
];

/** key → description lookup, derived from MERGE_FIELDS (used where only the key
 *  is known, e.g. the per-property document editor's palette). */
export const MERGE_DESCRIPTIONS: Record<string, string> = Object.fromEntries(
  MERGE_FIELDS.map((f) => [f.key, f.description]),
);
