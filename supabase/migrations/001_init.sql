-- ============================================================================
-- Palace Gate Lettings — Supabase schema (migration 001)
-- ============================================================================
-- Complete replacement for the Airtable base. Run this once against a fresh
-- Supabase project (SQL Editor → paste → Run) or any Postgres 14+ database
-- (it is also mounted into the local docker-compose dev Postgres).
--
-- Design notes
-- ------------
-- * Every Airtable table becomes a real relational table with snake_case
--   columns. The backend's db adapter (backend/app/db/schema.py) maps the
--   legacy Airtable field names (including the trailing-space oddities like
--   "Annual Rent ") onto these columns, so application logic is unchanged.
-- * Airtable "linked record" fields were symmetric many-to-many links.
--   Each link pair becomes one junction table; the adapter maintains and
--   reads both directions from it (no array-column drift).
-- * Airtable lookups (e.g. Properties.Stage_Order) are computed by the
--   adapter at read time from the junctions — no duplicated state.
-- * RLS is ENABLED with no policies on every table: the backend talks to
--   Postgres directly as the table owner (which bypasses RLS), while
--   Supabase's auto-generated REST/GraphQL endpoints are locked out for
--   anon/authenticated keys. Add policies later only if you want client-side
--   Supabase access.
-- * `payments` is new — it backs the Stripe integration (checkout sessions /
--   payment intents for holding deposits, deposits and rent).
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- updated_at maintenance
-- ----------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ============================================================================
-- 1. STAGES — reference table for the 9-step pipeline
-- ============================================================================
create table public.stages (
  id           uuid primary key default gen_random_uuid(),
  stage_name   text not null,
  stage_order  integer not null unique,
  -- Airtable "Stage agent" was a multipleCollaborators field — a JSON list of
  -- {"email": ..., "name": ...} objects. Empty list = fall back to ADMIN_EMAIL.
  stage_agent  jsonb not null default '[]'::jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create trigger trg_stages_updated before update on public.stages
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 2. PROPERTIES — the pipeline backbone
-- ============================================================================
create table public.properties (
  id                                  uuid primary key default gen_random_uuid(),

  -- identity / take-on
  address                             text,
  post_code                           text,
  type                                text,             -- "Rent"
  tenancy_type                        text,             -- "APT" | "Common Law"
  rent_frequency                      text,             -- "Monthly" | "Weekly"
  annual_rent                         numeric(12,2),    -- Airtable: "Annual Rent " (trailing space)
  landlord_email                      text,
  service_level                       text,             -- Full Management | Rent Collection | Let Only
  property_type                       text,

  -- gate machinery
  gate_status                         text,             -- "Clear" | "Blocked"
  gate_block_reason                   text,
  stage_changed_at                    date,

  -- compliance certificates
  epc_rating                          text,             -- Airtable: "EPC Rating " (trailing space)
  gas_cert_expiry                     date,             -- Airtable: "Gas Certificates Expiry"
  eicr_expiry                         date,
  gas_cert_status                     text,             -- On File | Palace Gate Arranging | Not Provided
  epc_status                          text,
  eicr_status                         text,
  smoke_detectors_fitted              boolean not null default false,

  -- consents / insurance (URL fields synced from the uploads manager)
  mortgage_consent_url                text,
  head_lease_url                      text,
  freeholder_consent_url              text,
  insurance_provider                  text,
  insurance_policy_number             text,
  insurance_certificate_url           text,

  -- signing flags
  tc_signed                           boolean not null default false,
  ta_ll_signed                        boolean not null default false,
  ta_tt_signed                        boolean not null default false,

  -- offer stage
  ll_offer_accepted                   boolean not null default false,
  anti_discrimination_confirmed       boolean not null default false,
  anti_discrimination_confirmed_date  date,
  hmo_flag                            boolean not null default false,
  hmo_licence_confirmed               boolean not null default false,
  holding_deposit_deadline            date,

  -- deposit / move-in
  tds_cert_on_file                    boolean not null default false,
  deposit_registered                  boolean not null default false,
  deposit_registration_date           date,
  deposit                             numeric(12,2),
  funds_cleared                       boolean not null default false,
  works_signed_off                    boolean not null default false,

  -- prescribed documents served
  how_to_rent_served                  boolean not null default false,
  gas_cert_served                     boolean not null default false,
  epc_served                          boolean not null default false,
  eicr_served                         boolean not null default false,
  tds_info_served                     boolean not null default false,
  rra_sheet_served                    boolean not null default false,
  rra_sheet_served_date               date,

  -- tenancy dates / misc
  tenancy_start_date                  date,
  tenancy_expiry_date                 date,
  checkin_date                        date,
  checkout_date                       date,
  inventory_clerk                     text,
  westminster_licence_number          text,

  created_at                          timestamptz not null default now(),
  updated_at                          timestamptz not null default now()
);
create index idx_properties_tenancy_type on public.properties (tenancy_type);
create index idx_properties_gate_status  on public.properties (gate_status);
create trigger trg_properties_updated before update on public.properties
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 3. LANDLORDS
-- ============================================================================
create table public.landlords (
  id                          uuid primary key default gen_random_uuid(),
  full_name                   text,
  email_address               text,
  mobile_number               text,
  full_address                text,
  post_code                   text,

  verification_status         text,    -- Pending Review | Approved | Rejected
  ta_signed                   boolean not null default false,
  tc_signed                   boolean not null default false,
  primary_for_disbursement    boolean not null default false,
  ownership_share_percent     numeric(6,2),

  -- residency / NRL
  uk_resident_status          text,    -- Resident | Non-resident
  nrl_withholding_active      boolean not null default false,
  nrl_approval_number         text,
  nrl_tax_cert_diary_set      boolean not null default false,

  -- disbursement banking
  bank_name                   text,
  sort_code                   text,
  account_name                text,
  account_number              text,

  -- block manager
  block_manager_name          text,
  block_manager_address       text,
  block_manager_postal_code   text,
  block_manager_contact       text,
  block_manager_email         text,

  -- verification / AML pack
  individual_or_company       text,
  id_document_type            text,
  id_document_url             text,
  visa_snapshot_url           text,
  address_doc_type            text,
  address_document_url        text,
  ownership_document_url      text,
  company_name                text,
  company_reg_number          text,
  company_reg_address         text,
  director_name               text,
  incorporation_doc_url       text,
  bank_statements_url         text,
  source_of_funds             text,
  purchase_explanation        text,
  id_name_match               text,    -- Pending | Confirmed | Mismatch
  aml_check_date              date,
  aml_checked_by              text,

  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);
create index idx_landlords_email on public.landlords (email_address);
create trigger trg_landlords_updated before update on public.landlords
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 4. TENANTS
-- ============================================================================
create table public.tenants (
  id                          uuid primary key default gen_random_uuid(),
  name                        text,
  tenant_email                text,
  tenant_address              text,

  start_date                  date,
  end_date                    date,
  tenancy_term                text,
  amount                      numeric(12,2),   -- monthly rent
  rent_frequency              text,
  deposit_amount              numeric(12,2),
  holding_deposit             numeric(12,2),
  rent_in_advance_months      integer,
  break_clause                numeric(12,2),   -- break-clause activation fee in £ (currency in Airtable)
  renew                       text,
  special_condition           text,

  guarantor_name              text,
  guarantor_address           text,            -- Airtable: "Gurantor Address" (sic)
  guarantor_email             text,
  is_student                  boolean not null default false,

  referencing_status          text,            -- Pending | Pass | Conditional | Fail
  referencing_recorded        boolean not null default false,
  referencing_paragon_ref     text,
  landlord_approval_received  boolean not null default false,

  ta_signed                   boolean not null default false,

  -- Right to Rent
  rtr_check_type              text,
  rtr_check_date              date,
  rtr_doc_reference           text,
  visa_expiry_date            date,

  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);
create index idx_tenants_email       on public.tenants (tenant_email);
create index idx_tenants_paragon_ref on public.tenants (referencing_paragon_ref);
create trigger trg_tenants_updated before update on public.tenants
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 5. OFFERS — offer lifecycle (one row per tenant offer)
-- ============================================================================
create table public.offers (
  id                        uuid primary key default gen_random_uuid(),
  name                      text,
  status                    text,            -- Pending | Accepted | Rejected_By_Landlord |
                                             -- Withdrawn_By_Tenant | Expired | Failed_Referencing | Superseded
  offered_rent              numeric(12,2),
  rent_frequency            text,
  deposit                   numeric(12,2),
  holding_deposit           numeric(12,2),
  start_date                date,
  end_date                  date,
  tenancy_term              text,
  holding_deposit_deadline  date,
  docusign_envelope_id      text,
  created_on                date,            -- Airtable "Created At" (date field set by app)
  closed_on                 date,            -- Airtable "Closed At"
  close_reason              text,
  created_by                text,
  notes                     text,
  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now()
);
create index idx_offers_status   on public.offers (status);
create index idx_offers_envelope on public.offers (docusign_envelope_id);
create trigger trg_offers_updated before update on public.offers
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 6. DIARY — scheduled alerts fired by PG_06
-- ============================================================================
create table public.diary (
  id             uuid primary key default gen_random_uuid(),
  diary_type     text,        -- Rent Review S13 | Gas Cert Renewal | EICR Renewal | NRL Tax Cert |
                              -- TDS 30-Day Countdown | Tenancy Expiry Warning | RTR Followup |
                              -- Break Clause Info | RRA Deadline | Reminder
  diary_date     date,
  alert_date     date,
  alert_message  text,
  assigned_to    text,
  fired          boolean not null default false,
  fired_date     date,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create index idx_diary_unfired on public.diary (alert_date) where fired = false;
create trigger trg_diary_updated before update on public.diary
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 7. FINANCIALS
-- ============================================================================
create table public.financials (
  id                   uuid primary key default gen_random_uuid(),
  commission_rate      numeric(6,4),
  disbursement_status  text,           -- Pending | ...
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);
create trigger trg_financials_updated before update on public.financials
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 8. CHECKLIST — Tenancy Checklist catalog + ad-hoc gate items
-- ============================================================================
create table public.checklist (
  id            uuid primary key default gen_random_uuid(),
  name          text,
  priority      text,            -- Critical | High | Medium | Low
  applies_to    jsonb not null default '[]'::jsonb,   -- list of tags (multipleSelects in Airtable)
  is_template   boolean not null default false,
  is_gate_item  boolean not null default false,
  status        text,            -- Todo | ...
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create trigger trg_checklist_updated before update on public.checklist
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 9. SUBMISSIONS — raw form-payload audit rows
-- ============================================================================
create table public.submissions (
  id              uuid primary key default gen_random_uuid(),
  form_name       text,
  submitted_date  date,
  json_data       text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create trigger trg_submissions_updated before update on public.submissions
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 10. GATE_LOG — audit of every gate evaluation
-- ============================================================================
create table public.gate_log (
  id                       uuid primary key default gen_random_uuid(),
  attempted_at             timestamptz,
  from_stage               text,
  to_stage                 text,
  result                   text,        -- Passed | Blocked
  block_reason             text,
  gate_warnings            text,
  gate_actions             text,
  gate_warnings_updated    date,
  gate_warnings_source     text,
  gate_warnings_dismissed  boolean not null default false,
  resolved_by              text,
  resolved_at              timestamptz,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);
create trigger trg_gate_log_updated before update on public.gate_log
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 11. COMPLIANCE — service trail for prescribed documents
-- ============================================================================
create table public.compliance (
  id              uuid primary key default gen_random_uuid(),
  document_type   text,
  served_date     date,
  served_to       text,
  served_as       text,        -- PDF Attachment | Link
  file_url        text,
  confirmed_sent  boolean not null default false,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create trigger trg_compliance_updated before update on public.compliance
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 12. SENT_DOCUMENTS — per-stage record of documents sent
-- ============================================================================
create table public.sent_documents (
  id              uuid primary key default gen_random_uuid(),
  name            text,
  doc_id          text,
  doc_name        text,
  stage           integer,
  channel         text,        -- Sign | Email PDF | Email HTML | Attachment
  recipients      text,
  sent_date       date,
  sent_by         text,
  pdf_url         text,
  envelope_id     text,
  status          text,        -- Sent | Delivered | Viewed | Signed | Declined | Voided
  completed_date  date,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index idx_sent_documents_envelope on public.sent_documents (envelope_id);
create trigger trg_sent_documents_updated before update on public.sent_documents
  for each row execute function public.set_updated_at();

-- ============================================================================
-- 13. PAYMENTS — Stripe integration (new table, no Airtable ancestor)
-- ============================================================================
create table public.payments (
  id                          uuid primary key default gen_random_uuid(),
  property_id                 uuid references public.properties (id) on delete set null,
  tenant_id                   uuid references public.tenants (id) on delete set null,
  offer_id                    uuid references public.offers (id) on delete set null,
  payment_type                text not null default 'other',  -- holding_deposit | deposit |
                                                              -- first_month_rent | rent | fee | other
  amount                      numeric(12,2) not null,
  currency                    text not null default 'gbp',
  status                      text not null default 'pending', -- pending | processing | succeeded |
                                                               -- failed | cancelled | refunded
  description                 text,
  stripe_checkout_session_id  text,
  stripe_payment_intent_id    text,
  stripe_customer_id          text,
  metadata                    jsonb not null default '{}'::jsonb,
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);
create index idx_payments_property on public.payments (property_id);
create index idx_payments_session  on public.payments (stripe_checkout_session_id);
create index idx_payments_intent   on public.payments (stripe_payment_intent_id);
create trigger trg_payments_updated before update on public.payments
  for each row execute function public.set_updated_at();

-- ============================================================================
-- JUNCTION TABLES — one per Airtable link-field pair (symmetric links)
-- ============================================================================
-- Properties.Stage  <->  Stages (single-valued in practice; junction keeps the
-- adapter uniform).
create table public.property_stage (
  property_id  uuid not null references public.properties (id) on delete cascade,
  stage_id     uuid not null references public.stages (id) on delete cascade,
  position     integer not null default 0,
  created_at   timestamptz not null default now(),
  primary key (property_id, stage_id)
);
create index idx_property_stage_stage on public.property_stage (stage_id);

-- Properties.Landlords  <->  Landlords.Properties
create table public.property_landlords (
  property_id  uuid not null references public.properties (id) on delete cascade,
  landlord_id  uuid not null references public.landlords (id) on delete cascade,
  position     integer not null default 0,
  created_at   timestamptz not null default now(),
  primary key (property_id, landlord_id)
);
create index idx_property_landlords_landlord on public.property_landlords (landlord_id);

-- Properties.Tenant — the ACCEPTED tenancy link. Deliberately a separate
-- relationship from Tenants."Property Id" (below): an offer's tenants point
-- at the property from creation, but the property only points back once that
-- offer is accepted (Gap 5 — competing offers must not clobber each other).
create table public.property_tenants (
  property_id  uuid not null references public.properties (id) on delete cascade,
  tenant_id    uuid not null references public.tenants (id) on delete cascade,
  position     integer not null default 0,
  created_at   timestamptz not null default now(),
  primary key (property_id, tenant_id)
);
create index idx_property_tenants_tenant on public.property_tenants (tenant_id);

-- Tenants."Property Id" — which property a tenant applied to (set at offer
-- creation, read e.g. by the Paragon webhook to find the gate to re-evaluate).
create table public.tenant_property_id (
  tenant_id    uuid not null references public.tenants (id) on delete cascade,
  property_id  uuid not null references public.properties (id) on delete cascade,
  position     integer not null default 0,
  created_at   timestamptz not null default now(),
  primary key (tenant_id, property_id)
);
create index idx_tenant_property_id_property on public.tenant_property_id (property_id);

-- Offers.Property  <->  Properties.Offers
create table public.offer_properties (
  offer_id     uuid not null references public.offers (id) on delete cascade,
  property_id  uuid not null references public.properties (id) on delete cascade,
  position     integer not null default 0,
  created_at   timestamptz not null default now(),
  primary key (offer_id, property_id)
);
create index idx_offer_properties_property on public.offer_properties (property_id);

-- Offers.Tenants  <->  Tenants.Offers
create table public.offer_tenants (
  offer_id    uuid not null references public.offers (id) on delete cascade,
  tenant_id   uuid not null references public.tenants (id) on delete cascade,
  position    integer not null default 0,
  created_at  timestamptz not null default now(),
  primary key (offer_id, tenant_id)
);
create index idx_offer_tenants_tenant on public.offer_tenants (tenant_id);

-- Diary.Property  <->  Properties.Diary
create table public.diary_properties (
  diary_id     uuid not null references public.diary (id) on delete cascade,
  property_id  uuid not null references public.properties (id) on delete cascade,
  position     integer not null default 0,
  created_at   timestamptz not null default now(),
  primary key (diary_id, property_id)
);
create index idx_diary_properties_property on public.diary_properties (property_id);

-- Financials.Property  <->  Properties.Financials
create table public.financials_properties (
  financial_id  uuid not null references public.financials (id) on delete cascade,
  property_id   uuid not null references public.properties (id) on delete cascade,
  position      integer not null default 0,
  created_at    timestamptz not null default now(),
  primary key (financial_id, property_id)
);
create index idx_financials_properties_property on public.financials_properties (property_id);

-- Submissions.Property  <->  Properties.Submissions
create table public.submissions_properties (
  submission_id  uuid not null references public.submissions (id) on delete cascade,
  property_id    uuid not null references public.properties (id) on delete cascade,
  position       integer not null default 0,
  created_at     timestamptz not null default now(),
  primary key (submission_id, property_id)
);
create index idx_submissions_properties_property on public.submissions_properties (property_id);

-- Gate_Log.Property  <->  Properties.Gate_Log
create table public.gate_log_properties (
  gate_log_id  uuid not null references public.gate_log (id) on delete cascade,
  property_id  uuid not null references public.properties (id) on delete cascade,
  position     integer not null default 0,
  created_at   timestamptz not null default now(),
  primary key (gate_log_id, property_id)
);
create index idx_gate_log_properties_property on public.gate_log_properties (property_id);

-- Compliance.Property  <->  Properties.Compliance
create table public.compliance_properties (
  compliance_id  uuid not null references public.compliance (id) on delete cascade,
  property_id    uuid not null references public.properties (id) on delete cascade,
  position       integer not null default 0,
  created_at     timestamptz not null default now(),
  primary key (compliance_id, property_id)
);
create index idx_compliance_properties_property on public.compliance_properties (property_id);

-- Compliance.Tenant  <->  Tenants.Compliance
create table public.compliance_tenants (
  compliance_id  uuid not null references public.compliance (id) on delete cascade,
  tenant_id      uuid not null references public.tenants (id) on delete cascade,
  position       integer not null default 0,
  created_at     timestamptz not null default now(),
  primary key (compliance_id, tenant_id)
);
create index idx_compliance_tenants_tenant on public.compliance_tenants (tenant_id);

-- Sent_Documents.Property  <->  Properties.Sent_Documents
create table public.sent_documents_properties (
  sent_document_id  uuid not null references public.sent_documents (id) on delete cascade,
  property_id       uuid not null references public.properties (id) on delete cascade,
  position          integer not null default 0,
  created_at        timestamptz not null default now(),
  primary key (sent_document_id, property_id)
);
create index idx_sent_documents_properties_property on public.sent_documents_properties (property_id);

-- Properties."Tenancy Checklist"  <->  Checklist.Properties
-- (the per-property ticks against the shared catalog)
create table public.property_checklist_items (
  property_id   uuid not null references public.properties (id) on delete cascade,
  checklist_id  uuid not null references public.checklist (id) on delete cascade,
  position      integer not null default 0,
  created_at    timestamptz not null default now(),
  primary key (property_id, checklist_id)
);
create index idx_property_checklist_items_item on public.property_checklist_items (checklist_id);

-- Checklist.Property  <->  Properties.Checklist
-- (ad-hoc per-property gate rows, e.g. "Confirm HMO licence")
create table public.checklist_properties (
  checklist_id  uuid not null references public.checklist (id) on delete cascade,
  property_id   uuid not null references public.properties (id) on delete cascade,
  position      integer not null default 0,
  created_at    timestamptz not null default now(),
  primary key (checklist_id, property_id)
);
create index idx_checklist_properties_property on public.checklist_properties (property_id);

-- ============================================================================
-- Row Level Security — lock the Supabase REST surface; the backend connects
-- directly as the table owner (which bypasses RLS), so it is unaffected.
-- ============================================================================
alter table public.stages                     enable row level security;
alter table public.properties                 enable row level security;
alter table public.landlords                  enable row level security;
alter table public.tenants                    enable row level security;
alter table public.offers                     enable row level security;
alter table public.diary                      enable row level security;
alter table public.financials                 enable row level security;
alter table public.checklist                  enable row level security;
alter table public.submissions                enable row level security;
alter table public.gate_log                   enable row level security;
alter table public.compliance                 enable row level security;
alter table public.sent_documents             enable row level security;
alter table public.payments                   enable row level security;
alter table public.property_stage             enable row level security;
alter table public.property_landlords         enable row level security;
alter table public.property_tenants           enable row level security;
alter table public.tenant_property_id         enable row level security;
alter table public.offer_properties           enable row level security;
alter table public.offer_tenants              enable row level security;
alter table public.diary_properties           enable row level security;
alter table public.financials_properties      enable row level security;
alter table public.submissions_properties     enable row level security;
alter table public.gate_log_properties        enable row level security;
alter table public.compliance_properties      enable row level security;
alter table public.compliance_tenants         enable row level security;
alter table public.sent_documents_properties  enable row level security;
alter table public.property_checklist_items   enable row level security;
alter table public.checklist_properties       enable row level security;

-- ============================================================================
-- SEED DATA
-- ============================================================================
-- The 9 pipeline stages the gate evaluator drives. stage_agent is left empty
-- ([]) — agent-summary emails then fall back to ADMIN_EMAIL. To route a stage
-- to a specific agent:
--   update stages set stage_agent = '[{"email":"agent@palacegate.co.uk","name":"Agent"}]'
--   where stage_order = 4;
insert into public.stages (stage_name, stage_order) values
  ('Take-on',        1),
  ('Compliance',     2),
  ('Marketing',      3),
  ('Offer',          4),
  ('Referencing',    5),
  ('TA Signing',     6),
  ('Pre Move-in',    7),
  ('Live Tenancy',   8),
  ('End of Tenancy', 9);

-- NOTE: the Tenancy Checklist catalog is intentionally NOT seeded. The
-- tenant-pack guard requires EVERY catalog row to be ticked per property, so
-- an empty catalog means no checklist blocking out of the box. Add your
-- standard items (is_template = true) when you are ready:
--   insert into checklist (name, priority, is_template) values ('Keys cut', 'High', true);

commit;
