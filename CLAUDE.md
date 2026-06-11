# CLAUDE.md — LettingAuto (commercial branch)

## What this is

Multi-tenant SaaS for UK letting agencies: a 9-stage tenancy pipeline
(take-on → compliance → marketing → offer → referencing → TA signing →
pre-move-in → live → end) with compliance gates, e-signing, landlord/tenant
forms, and Stripe billing. FastAPI backend (`backend/`), React 18 + Vite +
Tailwind frontend (`frontend/`), Supabase Postgres datastore.

**Branch discipline (important):** `supabase-stripe-integration` is the
commercial multi-agency product — work here. The `dev*` branches are the
single-tenant Palace Gate client product on Airtable — do NOT apply
commercial changes to them.

## Commands

```bash
# Backend tests (62 unit tests; APP_ENV=test disables cache + uses mock signer)
cd backend && APP_ENV=test python -m pytest tests -q

# End-to-end smoke vs a real DB (37 checks incl. multi-tenant isolation).
# Creates and deletes its own data — safe on the live project.
cd backend && python -m scripts.smoke_supabase

# Frontend typecheck / build
cd frontend && npx tsc --noEmit && npx vite build

# Local Postgres stand-in for Supabase (schema auto-applied from supabase/migrations)
docker compose -f docker-compose.dev.yml up -d db   # localhost:54322
# reset schema: docker compose -f docker-compose.dev.yml down -v

# Apply migrations to whatever SUPABASE_DB_URL points at (incl. live Supabase)
cd backend && python -m scripts.apply_migrations
```

Backend runs with `uvicorn app.main:app --port 8000`. Frontend `npm run dev`
(5173). CORS allows only `FRONTEND_BASE_URL` + localhost:5173 — a dev server
on another port will be CORS-blocked.

## Architecture — the things you can't guess from filenames

### Data layer keeps the Airtable wire-shape (deliberate)
All handlers/routers/services do `from app.db import supabase_client as at`
and speak **legacy Airtable field names** — including `"Annual Rent "` and
`"EPC Rating "` (trailing spaces are real) and `"Gurantor Address"` (sic).
Records look like `{"id", "fields": {...}, "createdTime"}`. The translation
to real Postgres columns lives ONLY in `backend/app/db/schema.py` (registry)
+ `supabase_client.py` (adapter). To add a field: column in a new migration +
one registry entry — never rename the app-facing names.

- Filters are structured: `at.eq/and_/or_/is_before` (no formula strings).
  `eq(field, False)` matches false AND null (Airtable checkbox semantics).
- Linked records = junction tables, symmetric both ways. EXCEPTION:
  `Tenants."Property Id"` (set at offer) and `Properties.Tenant` (set only on
  offer ACCEPTANCE) are two separate relations — that separation is the
  competing-offers design (Gap 5); do not "fix" it into one.
- `Properties.Stage_Order` is computed at read time (lookup), read-only.

### Multi-tenancy = the agency scope ContextVar
`require_agent` (core/auth.py) resolves the Supabase JWT → `agency_users`
membership → `at.set_agency_scope(agency_id)`. The adapter then auto-filters
every read, stamps `agency_id` on create, and 404s cross-agency
get/update/delete. **Any new webhook/public entrypoint must establish scope**
(see pg04, webhooks.py, forms.py for the pattern) or its writes land with
agency_id NULL and become invisible to agents. RLS in the DB is
defense-in-depth only — the backend connects as table owner and bypasses it.

Auth: Supabase tokens are **ES256** (new projects) verified via the project
JWKS; HS256 secret is the legacy fallback. `ALLOW_BOOTSTRAP_LOGIN=true` gives
a dev password login that auto-provisions a "Bootstrap Agency".

### Billing = pay-first take-on (deferred fulfillment)
£50 one-time per new tenancy, nothing recurring. Submitting the new-property
form creates NOTHING — the payload is stored on a pending `payments` row
(`metadata.takeon_payload`) + a Stripe Checkout Session. Fulfillment
(`billing.mark_paid_and_fulfill`) runs from BOTH the webhook and the
success-page poller; `at.try_transition` (status CAS pending→succeeded) makes
it exactly-once. With no `STRIPE_SECRET_KEY`, billing is disabled and take-on
creates immediately (dev mode).

### Branding is per-agency at runtime
`app/core/branding.get_brand()` resolves the CURRENT agency's name/colours
for emails, contract PDFs, prescribed docs, merge fields ({{agency_name}}).
Platform fallback = "LettingAuto". Never hardcode an agency name. The cert
status select value is `"Agency Arranging"` (renamed from "Palace Gate
Arranging" — a legacy lowercase key remains in derivations.py on purpose).

### Frontend design system: "Editorial Mesh" (landing variation F)
Warm paper + ink + Fraunces serif (italic accents) + pastel mesh + ink pill
buttons. It's token-driven: the Tailwind "navy" scale IS the ink ramp
(text-navy-700 renders ink, not blue) and cream is the paper ramp — restyle
via `tailwind.config.js` + `styles.css` primitives (`card`, `btn-primary`,
`input`, `kicker`, `bg-mesh-hero/-corner`), not per-page hex. Landing drafts:
`frontend/design-previews/` (F chosen).

## Gotchas that have actually bitten

- **Windows encoding:** many backend files contain UTF-8 em-dashes that
  PowerShell reads as mojibake. For edits, anchor on ASCII-only lines; for
  scripted rewrites use `[System.IO.File]::ReadAllText($p, UTF8)` +
  `WriteAllText` with BOM-less UTF8. Never iterate PowerShell array-of-arrays
  built with `@(@('a','b'))` — single-pair arrays flatten and `$pair[0]`
  becomes a CHARACTER (this once mass-corrupted three files).
- Console output: set `PYTHONIOENCODING=utf-8` before running scripts that
  print arrows/ticks.
- `backend/.env` is gitignored and holds real secrets (Supabase DB URL,
  Stripe test keys). `.env.example` is the committed reference.
- Stripe's hosted checkout cannot be automated headlessly (hCaptcha); test
  the webhook by signing events with `STRIPE_WEBHOOK_SECRET` (HMAC-SHA256 of
  `"{t}.{payload}"`), or pay manually with 4242….
- Port 8000 is often occupied by the user's own backend — run test instances
  on another port and don't kill processes you didn't start.

## Key docs

- `docs/COMMERCIAL_SETUP.md` — everything the operator configures (Supabase,
  OAuth providers, Stripe, env vars, first-run walkthrough).
- `docs/SUPABASE_MIGRATION.md` — how/why the Airtable→Supabase adapter works.
- `supabase/migrations/` — 001 schema+seed, 002 agencies/RLS. Append-only;
  new DDL = new file (001/002 are already applied to the live project).
