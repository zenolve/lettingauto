-- 004: version the documents an agency sends
--
-- A document is often revised after it goes out (a wrong rent, a changed
-- clause, a missed signer). Until now a resend was just another unrelated
-- sent_documents row: nothing said it replaced the earlier send, the earlier
-- send stayed "current", and an email-only send kept no copy of what it said.
--
--   version        1 for a first send; a revision is the previous version + 1
--   revises_id     the send this one replaces (null for a first send)
--   superseded_at  set on a send when a revision of it goes out
--
-- The exact HTML each send delivered lives in sent_document_bodies rather than
-- on sent_documents, so listing a property's sends does not drag every body
-- (a tenancy agreement is 70-130 KB) along with it.
--
-- Additive and idempotent: existing rows become version 1 with no history, and
-- code that predates this migration keeps working unchanged.
begin;

alter table public.sent_documents
  add column if not exists version integer not null default 1;
alter table public.sent_documents
  add column if not exists revises_id uuid references public.sent_documents (id) on delete set null;
alter table public.sent_documents
  add column if not exists superseded_at timestamptz;

create index if not exists idx_sent_documents_revises on public.sent_documents (revises_id);

create table if not exists public.sent_document_bodies (
  id                uuid primary key default gen_random_uuid(),
  agency_id         uuid references public.agencies (id) on delete cascade,
  sent_document_id  uuid not null unique references public.sent_documents (id) on delete cascade,
  body_html         text not null,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create index if not exists idx_sent_document_bodies_agency on public.sent_document_bodies (agency_id);

drop trigger if exists trg_sent_document_bodies_updated on public.sent_document_bodies;
create trigger trg_sent_document_bodies_updated before update on public.sent_document_bodies
  for each row execute function public.set_updated_at();

-- Same posture as every other table (001/002): RLS on, members may read their
-- own agency's rows, writes are backend-only.
alter table public.sent_document_bodies enable row level security;
drop policy if exists member_select on public.sent_document_bodies;
create policy member_select on public.sent_document_bodies
  for select using (agency_id in (select agency_id from public.agency_users where user_id = auth.uid()));

commit;
