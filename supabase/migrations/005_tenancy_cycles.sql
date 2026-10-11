-- 005: end a tenancy and re-let the same property
--
-- A property row has always carried its one tenancy: the signatures, deposit
-- and served flags sit beside the landlord and the certificates, and the stage
-- is derived from those flags. That left no way to finish a tenancy and start
-- the next on the same property without re-entering the landlord.
--
--   properties.tenancy_ended_date        set by "End tenancy"; derives stage 9
--   properties.tenancy_cycle_started_at  set by "Re-let"; everything tenancy-
--                                        related before it belongs to an
--                                        archived tenancy
--   tenancies                            one row per archived tenancy: who,
--                                        when, the terms, and a snapshot of
--                                        every tenancy field as it stood
--
-- Additive and idempotent; code that predates it is unaffected.
begin;

alter table public.properties
  add column if not exists tenancy_ended_date date;
alter table public.properties
  add column if not exists tenancy_cycle_started_at timestamptz;

create table if not exists public.tenancies (
  id              uuid primary key default gen_random_uuid(),
  agency_id       uuid references public.agencies (id) on delete cascade,
  property_id     uuid not null references public.properties (id) on delete cascade,
  sequence        integer not null,      -- 1 = the property's first archived tenancy
  tenant_names    text,                  -- as they stood when the tenancy ended
  start_date      date,
  end_date        date,
  rent            numeric,
  rent_frequency  text,
  deposit         numeric,
  tenancy_type    text,
  snapshot        jsonb,                 -- every tenancy field + linked ids at archive time
  archived_by     text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index if not exists idx_tenancies_property on public.tenancies (property_id);
create index if not exists idx_tenancies_agency   on public.tenancies (agency_id);

drop trigger if exists trg_tenancies_updated on public.tenancies;
create trigger trg_tenancies_updated before update on public.tenancies
  for each row execute function public.set_updated_at();

-- Same posture as every other table: RLS on, members read their own agency's
-- rows, writes are backend-only.
alter table public.tenancies enable row level security;
drop policy if exists member_select on public.tenancies;
create policy member_select on public.tenancies
  for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));

commit;
