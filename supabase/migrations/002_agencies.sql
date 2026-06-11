-- ============================================================================
-- Migration 002 — multi-agency SaaS (commercial product)
-- ============================================================================
-- Adds the agency layer on top of 001_init.sql:
--   * agencies        — one row per onboarded letting agency (branding + billing)
--   * agency_users    — membership: Supabase auth user ↔ agency + role
--   * agency_id       — tenant-isolation column on every operational table
--   * RLS policies    — defense-in-depth: Supabase-auth'd users can only ever
--                       reach their own agency's rows through the auto REST
--                       API. The backend itself connects as the table owner
--                       (bypasses RLS) and additionally enforces the same
--                       scoping in the app layer on every query.
--
-- Run AFTER 001_init.sql. Idempotent enough for a fresh project; not designed
-- to re-run over itself.
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- auth.uid() shim — exists natively on Supabase; created here only for plain
-- Postgres (the docker-compose dev database) so the policies below parse.
-- ----------------------------------------------------------------------------
create schema if not exists auth;
do $$
begin
  if not exists (
    select 1 from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'auth' and p.proname = 'uid'
  ) then
    create function auth.uid() returns uuid
    language sql stable
    as 'select nullif(current_setting(''request.jwt.claim.sub'', true), '''')::uuid';
  end if;
end
$$;

-- ============================================================================
-- AGENCIES
-- ============================================================================
create table public.agencies (
  id                       uuid primary key default gen_random_uuid(),
  name                     text not null,
  slug                     text unique,
  email                    text,                      -- main contact / notification inbox
  phone                    text,
  office_address           text,
  website                  text,
  logo_url                 text,

  -- branding applied to contracts, emails and PDFs
  brand_navy               text not null default '#004AAD',
  brand_gold               text not null default '#C9A24C',

  -- product state
  onboarding_completed     boolean not null default false,

  -- Stripe billing (£50 one-time per new tenancy + £5/month per live tenancy)
  stripe_customer_id       text,
  stripe_subscription_id   text,
  subscription_status      text not null default 'none',  -- none | active | past_due |
                                                          -- canceled | incomplete
  payment_method_on_file   boolean not null default false,
  billing_email            text,

  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);
create index idx_agencies_stripe_customer on public.agencies (stripe_customer_id);
create trigger trg_agencies_updated before update on public.agencies
  for each row execute function public.set_updated_at();

-- ============================================================================
-- AGENCY USERS — Supabase auth user ↔ agency membership
-- ============================================================================
create table public.agency_users (
  id           uuid primary key default gen_random_uuid(),
  agency_id    uuid not null references public.agencies (id) on delete cascade,
  user_id      uuid not null unique,     -- auth.users.id (one agency per user, v1)
  email        text not null,
  full_name    text,
  role         text not null default 'owner',   -- owner | admin | agent
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index idx_agency_users_agency on public.agency_users (agency_id);
create index idx_agency_users_user   on public.agency_users (user_id);
create trigger trg_agency_users_updated before update on public.agency_users
  for each row execute function public.set_updated_at();

-- ============================================================================
-- TENANT-ISOLATION COLUMN on every operational table
-- (stages stays global platform reference data)
-- ============================================================================
alter table public.properties     add column agency_id uuid references public.agencies (id) on delete cascade;
alter table public.landlords      add column agency_id uuid references public.agencies (id) on delete cascade;
alter table public.tenants        add column agency_id uuid references public.agencies (id) on delete cascade;
alter table public.offers         add column agency_id uuid references public.agencies (id) on delete cascade;
alter table public.diary          add column agency_id uuid references public.agencies (id) on delete cascade;
alter table public.financials     add column agency_id uuid references public.agencies (id) on delete cascade;
alter table public.checklist      add column agency_id uuid references public.agencies (id) on delete cascade;
alter table public.submissions    add column agency_id uuid references public.agencies (id) on delete cascade;
alter table public.gate_log       add column agency_id uuid references public.agencies (id) on delete cascade;
alter table public.compliance     add column agency_id uuid references public.agencies (id) on delete cascade;
alter table public.sent_documents add column agency_id uuid references public.agencies (id) on delete cascade;
alter table public.payments       add column agency_id uuid references public.agencies (id) on delete cascade;

create index idx_properties_agency     on public.properties (agency_id);
create index idx_landlords_agency      on public.landlords (agency_id);
create index idx_tenants_agency        on public.tenants (agency_id);
create index idx_offers_agency         on public.offers (agency_id);
create index idx_diary_agency          on public.diary (agency_id);
create index idx_financials_agency     on public.financials (agency_id);
create index idx_checklist_agency      on public.checklist (agency_id);
create index idx_submissions_agency    on public.submissions (agency_id);
create index idx_gate_log_agency       on public.gate_log (agency_id);
create index idx_compliance_agency     on public.compliance (agency_id);
create index idx_sent_documents_agency on public.sent_documents (agency_id);
create index idx_payments_agency       on public.payments (agency_id);

-- Payments: the £50 tenancy setup fee is invoiced against the subscription's
-- customer — keep the invoice id for reconciliation.
alter table public.payments add column stripe_invoice_id text;

-- ============================================================================
-- RLS — enable on the new tables; membership-scoped policies everywhere.
-- The backend (table owner) bypasses these; they protect the Supabase
-- auto-generated REST/GraphQL surface if anon/authenticated keys are ever
-- used client-side.
-- ============================================================================
alter table public.agencies     enable row level security;
alter table public.agency_users enable row level security;

create policy agency_self_select on public.agencies
  for select using (
    id in (select agency_id from public.agency_users where user_id = auth.uid())
  );

create policy agency_users_self_select on public.agency_users
  for select using (user_id = auth.uid());

-- Entity tables: members may read their own agency's rows. Writes remain
-- backend-only (no insert/update/delete policies).
create policy member_select on public.properties     for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));
create policy member_select on public.landlords      for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));
create policy member_select on public.tenants        for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));
create policy member_select on public.offers         for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));
create policy member_select on public.diary          for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));
create policy member_select on public.financials     for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));
create policy member_select on public.checklist      for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));
create policy member_select on public.submissions    for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));
create policy member_select on public.gate_log       for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));
create policy member_select on public.compliance     for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));
create policy member_select on public.sent_documents for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));
create policy member_select on public.payments       for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));

-- Stages are global reference data — readable by any signed-in user.
create policy stages_read on public.stages for select using (auth.uid() is not null);

commit;
