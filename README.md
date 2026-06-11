# LettingAuto — lettings workflow automation for agencies

> **This branch (`supabase-stripe-integration`) is the commercial multi-agency
> SaaS.** Agencies self-register (Supabase auth: email / Google / Microsoft),
> pay via Stripe (a one-time £50 per new tenancy), and every
> document/email carries their own branding. Full setup checklist:
> **[docs/COMMERCIAL_SETUP.md](docs/COMMERCIAL_SETUP.md)**.
> The `dev*` branches remain the single-tenant Palace Gate product.

A full-stack lettings-workflow platform (originally a replacement for a
Tally + n8n + Airtable pipeline). This bundle contains:

- **`backend/`** — FastAPI service (Python 3.11+) over Supabase/Postgres. The
  canonical form ingress is the JSON API at `/api/forms/*`; the legacy Tally
  webhook routes are kept as inert shells.
- **`frontend/`** — React 18 + Vite + Tailwind. Agency onboarding + settings,
  agent dashboard, property pipeline, entity editors, and a Tiptap-based
  contract editor that renders to PDF and pushes to e-signature.

> **Platform brand:** LettingAuto navy `#004AAD` / gold `#C9A24C` — overridden
> per agency at runtime.

## Quick start

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # then fill in real values
uvicorn app.main:app --reload --port 8000
```

The API is then on `http://localhost:8000`. Open `http://localhost:8000/docs`
for the interactive OpenAPI explorer.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env                                # set VITE_API_URL
npm run dev
```

App is on `http://localhost:5173`. Sign in with whatever email/password you put
in the backend `.env` as `AGENT_BOOTSTRAP_EMAIL` / `AGENT_BOOTSTRAP_PASSWORD`.

## Architecture

```
┌──────────────┐         ┌─────────────────────┐
│   React UI   │         │  Tally webhook shell│
│  (Vite app)  │         │  (inert — see note) │
└──────┬───────┘         └──────────┬──────────┘
       │ REST + JSON                │ (no longer in use)
       ▼                            ▼
   ┌──────────────────────────────────────┐
   │            FastAPI Backend           │
   │  routers/forms.py ─ internal forms   │
   │  webhooks/ ─ DocuSeal (+ Tally shell)│
   │  handlers/ ─ PG_00 .. PG_07 logic    │
   └──────────────┬───────────────────────┘
                  │
        ┌─────────┴──────────┬────────────────┬───────────────┐
        ▼                    ▼                ▼               ▼
   ┌──────────┐        ┌──────────┐    ┌────────────┐  ┌──────────┐
   │ Supabase │        │ DocuSeal │    │   SMTP     │  │  Stripe  │
   │(Postgres)│        │ (sign)   │    │ (notify)   │  │(payments)│
   └──────────┘        └──────────┘    └────────────┘  └──────────┘
```

> **Data layer:** Supabase (Postgres). Apply
> `supabase/migrations/001_init.sql` once and set `SUPABASE_DB_URL` — see
> [docs/SUPABASE_MIGRATION.md](docs/SUPABASE_MIGRATION.md). Locally,
> `docker compose -f docker-compose.dev.yml up` starts a Postgres with the
> schema pre-applied.

### Form parity

The internal API is the canonical path. The "Backend webhook (legacy)" column is
the original Tally landing route — kept as an inert shell for now but not used
in production and not protected by a Tally signing secret.

| Stage | Spec form | Internal route | Backend internal API | Backend webhook (legacy, inert) |
|-------|-----------|----------------|----------------------|---------------------------------|
| PG_01 | Agent Add Property    | `/agent/properties/new`          | `POST /api/forms/property-takeon`        | `POST /webhook/property-takeon`       |
| PG_02 | Landlord Admin        | `/landlord/admin?token=…`        | `POST /api/forms/landlord-admin`         | `POST /webhook/landlord-admin`        |
| PG_02b| Landlord Verification | `/landlord/verify?token=…`       | `POST /api/forms/landlord-verification`  | `POST /webhook/landlord-verification` |
| PG_03 | Offer                 | `/agent/properties/:id/offer`    | `POST /api/forms/offer`                  | `POST /webhook/offer`                 |
| PG_04 | DocuSeal events       | (no UI)                          | n/a                                       | `POST /webhook/docuseal-signed`       |
| PG_05 | Tenant pack           | `/agent/properties/:id/move-in`  | `POST /api/forms/tenant-pack`            | `POST /webhook/tenant-pack`           |
| PG_06 | Daily scheduler       | (cron)                           | `POST /internal/run-scheduler`           | (same)                                |
| PG_07 | RRA batch             | `/agent/admin/rra-batch`         | `POST /webhook/rra-batch`                | (same)                                |

### Contract editor

The contract editor lives at `/agent/properties/:id/contracts/:template`. It
uses **Tiptap** (ProseMirror) for the editing surface and renders mustache-style
merge fields (`{{landlord_full_name}}`, `{{property_address}}`, …) from the
linked database records on first open. The user can freely edit the body. On
submit, the backend converts the saved HTML to PDF (WeasyPrint) and creates a
DocuSeal submission with that PDF as the document and the right signing roles
filled in.

Three templates ship pre-populated:

1. **Terms & Conditions** (T&C) — landlord-only signature
2. **Offer Letter** — landlord-only signature, triggered from PG_03
3. **Tenancy Agreement** — APT and Common Law variants, both parties sign

See `backend/app/templates/contracts/*.html`.

## What's done vs what still needs Palace Gate input

Done:

- Full project structure, config, env scaffolding
- Supabase (Postgres) data layer — relational schema in `supabase/migrations/`,
  Airtable-shape adapter in `backend/app/db/supabase_client.py`
- Stripe payments scaffold (checkout sessions + webhook → `payments` table)
- DocuSeal client with submission + webhook signature verification
- SMTP email client with Palace Gate branding
- Gate evaluator (PG_00) — all stage transitions encoded
- PG_01 / PG_02 / PG_02b / PG_03 / PG_04 handlers, end-to-end
- PG_05 / PG_06 / PG_07 handlers
- Internal form submission endpoints (the canonical path; Tally retired)
- Tally parser retained as a dormant shell for the legacy webhook routes
- Contract editor backend (HTML → PDF → DocuSeal)
- React UI: agent auth, dashboard, property detail, all 4 forms, contract editor
- Branded email templates

Still needs Palace Gate input (see spec §10):

- DocuSeal template IDs (15, 16, 18, 20, 22 are placeholders in `config.py`)
- A Supabase project + its `SUPABASE_DB_URL` (run `supabase/migrations/001_init.sql` once)
- SMTP credentials + DocuSeal API token + Stripe keys (drop into `.env`)
- Lesley's email for NRL diary assignments
- Populate `stages.stage_agent` with the per-stage agent emails (seeded empty;
  summaries fall back to `ADMIN_EMAIL`)

All of these are marked with `# TODO(palace-gate):` comments in code.

## Repo layout

```
backend/
  app/
    main.py
    config.py
    db/
      supabase_client.py  # Postgres adapter (Airtable-shape records)
      schema.py           # field-name -> column registry
    core/
      auth.py
      email_client.py
      docuseal_client.py
      pdf_renderer.py
      logger.py
    parsers/
      tally_parser.py     # dormant; only referenced by legacy webhook shells
    handlers/
      pg00_gate.py
      pg01_takeon.py
      pg02_admin.py
      pg02b_verification.py
      pg03_offer.py
      pg04_docuseal.py
      pg05_tenant_pack.py
      pg06_scheduler.py
      pg07_rra_batch.py
    routers/
      auth.py
      properties.py
      landlords.py
      tenants.py
      forms.py            # internal form submissions (UI uses these)
      contracts.py        # contract editor / DocuSeal
      webhooks.py         # legacy Tally + DocuSeal callbacks
    models/
      property.py
      landlord.py
      tenant.py
      common.py
    services/
      compliance.py       # all PG_02 compliance checks
      apt.py              # APT validation
      derivations.py      # service level, cert status, tenancy type
      merge_fields.py     # populate contract templates
    templates/
      emails/
      contracts/
  requirements.txt
  .env.example
  tests/
    test_parsers.py
    test_derivations.py
    test_apt.py
    test_gate.py
frontend/
  package.json
  vite.config.ts
  tailwind.config.js
  index.html
  src/
    main.tsx
    App.tsx
    lib/
      api.ts
      auth.ts
      brand.ts
    components/
      ui/
      layout/
      forms/
      ContractEditor.tsx
    pages/
      Login.tsx
      Dashboard.tsx
      PropertyDetail.tsx
      forms/
        PropertyTakeon.tsx
        LandlordAdmin.tsx
        LandlordVerification.tsx
        Offer.tsx
        MoveIn.tsx
      ContractEditorPage.tsx
```
