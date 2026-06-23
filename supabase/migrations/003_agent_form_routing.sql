-- 003: route landlord onboarding forms to the agent
--
-- When the take-on "send admin form to landlord" box is OFF, the landlord
-- admin form (PG_01) and the downstream verification form (PG_02) are emailed
-- to the agent instead of the landlord. The verification send happens later,
-- in a public no-auth context, so the routing decision + the recipient email
-- are persisted on the property at take-on.
--
-- Idempotent (IF NOT EXISTS) so it is safe to apply to the already-populated
-- live project without re-running 001/002.
begin;

alter table public.properties
  add column if not exists forms_route_to_agent boolean not null default false;
alter table public.properties
  add column if not exists agent_forms_email text;

commit;
