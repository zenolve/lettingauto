# LettingAuto — commercial product setup guide

Everything YOU need to configure to run the multi-agency SaaS on this branch
(`supabase-stripe-integration`). Work top-to-bottom; each section ends with
the env vars it produces.

The other branches remain the single-tenant Palace Gate product — nothing
here applies to them.

---

## 1. Supabase project (database + auth)

1. Create a project at [supabase.com](https://supabase.com) (region close to you, e.g. London).
2. **Schema** — SQL Editor → run, in order:
   - [`supabase/migrations/001_init.sql`](../supabase/migrations/001_init.sql)
   - [`supabase/migrations/002_agencies.sql`](../supabase/migrations/002_agencies.sql)
3. **Connection string** — Settings → Database → Connection string → *Session pooler* (port 5432). Replace `[YOUR-PASSWORD]`.
4. **API keys** — Settings → API:
   - Project URL → `VITE_SUPABASE_URL` (frontend) and optionally `SUPABASE_URL` (backend)
   - `anon` `public` key → `VITE_SUPABASE_ANON_KEY` (frontend)
   - **JWT Secret** → `SUPABASE_JWT_SECRET` (backend — this is how the API verifies sign-ins)

```env
# backend/.env
SUPABASE_DB_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
SUPABASE_JWT_SECRET=<from Settings → API>
ALLOW_BOOTSTRAP_LOGIN=false        # true only for local dev

# frontend/.env
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key>
```

### 1a. Google sign-in

1. [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials → **Create OAuth client ID** (type: Web application).
2. Authorised redirect URI: `https://<ref>.supabase.co/auth/v1/callback`.
3. Copy Client ID + Secret into Supabase → Authentication → Providers → **Google** → enable.

### 1b. Microsoft sign-in (the `azure` provider)

1. [Azure Portal](https://portal.azure.com) → Microsoft Entra ID → App registrations → **New registration**.
   - Supported account types: *Accounts in any organizational directory and personal Microsoft accounts* (so any agency can sign in).
   - Redirect URI (Web): `https://<ref>.supabase.co/auth/v1/callback`.
2. Certificates & secrets → new client secret.
3. Supabase → Authentication → Providers → **Azure** → enable, paste Application (client) ID + secret.

### 1c. Auth URLs

Supabase → Authentication → URL Configuration:
- **Site URL**: your app origin (e.g. `https://app.yourdomain.com`, or `http://localhost:5173` for dev).
- **Redirect URLs**: add `http://localhost:5173/agent` and `https://app.yourdomain.com/agent`.

Email confirmations are on by default (Authentication → Providers → Email) —
fine to keep; users confirm then sign in.

---

## 2. Stripe (agency billing + payments)

Pricing model implemented: **£50 one-time per new tenancy** (charged at
property take-on against the agency's saved card) + **£5/month per live
tenancy** (one subscription per agency whose quantity tracks live tenancies).

1. [dashboard.stripe.com](https://dashboard.stripe.com) → Products → **Add product**:
   - Name: `Live tenancy` — Price: **£5.00 GBP, Recurring monthly**, *per unit*.
   - Copy the price id (`price_…`) → `STRIPE_PRICE_LIVE_TENANCY`.
   - (The £50 fee needs no product — it's created as an ad-hoc invoice item.)
2. Developers → API keys → **Secret key** → `STRIPE_SECRET_KEY`.
3. Developers → Webhooks → **Add endpoint**: `https://<your-api-domain>/webhook/stripe`
   with events:
   - `checkout.session.completed`
   - `checkout.session.expired`
   - `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`
   - `invoice.payment_failed`
   - `payment_intent.payment_failed`
   - `charge.refunded`
   Copy the signing secret (`whsec_…`) → `STRIPE_WEBHOOK_SECRET`.
4. Local testing: `stripe listen --forward-to localhost:8000/webhook/stripe`
   (use the printed `whsec_…`).

```env
# backend/.env
STRIPE_SECRET_KEY=sk_live_…        # or sk_test_…
STRIPE_WEBHOOK_SECRET=whsec_…
STRIPE_PRICE_LIVE_TENANCY=price_…
STRIPE_TENANCY_SETUP_FEE_PENCE=5000
STRIPE_CURRENCY=gbp
```

**How it behaves:** an agency adds a card in *Settings → Billing* (Stripe
Checkout, setup mode) → the webhook stores the default payment method and
starts the £5/unit subscription at quantity 0 → each take-on invoices £50
immediately (failure blocks the take-on with HTTP 402) → the subscription
quantity re-syncs whenever a tenancy goes live and nightly via the scheduler.
With no Stripe keys configured, billing is disabled and everything is free
(dev mode).

---

## 3. SMTP, signing, referencing (unchanged mechanics, new branding)

- `SMTP_*`, `FROM_EMAIL`, `ADMIN_EMAIL` — as before; all outbound email is now
  branded with **the sending agency's** name/colours automatically.
- DocuSign (`DOCUSIGN_*` + `docusign_rsa.key`) for production signing;
  `APP_ENV=test` uses the built-in mock signer.
- Paragon (`PARAGON_TOKEN`) optional — mock referencing otherwise.

---

## 4. Run it

**Local (no Supabase/Stripe accounts needed):**

```bash
docker compose -f docker-compose.dev.yml up      # db (schema auto-applied) + api + web
# leave SUPABASE_JWT_SECRET + VITE_SUPABASE_URL blank → dev bootstrap login
#   (AGENT_BOOTSTRAP_EMAIL / AGENT_BOOTSTRAP_PASSWORD; auto-creates "Bootstrap Agency")
# sanity check:
cd backend && python -m scripts.smoke_supabase   # 37 end-to-end checks incl. isolation
```

**Production (droplet):** as per [DEPLOY.md](../DEPLOY.md), plus the env vars
above and `ALLOW_BOOTSTRAP_LOGIN=false`.

---

## 5. First-run walkthrough (what an agency sees)

1. Sign in with Google / Microsoft / email → no membership yet → **Set up your
   agency** screen (name, contact, address).
2. Four-slide onboarding modal (pipeline → compliance → e-sign/payments →
   pricing). Dismiss persists on the agency record.
3. *Settings* → agency profile + document branding (colours drive contract
   PDFs and emails) + *Billing* → **Add payment method**.
4. *New property* → £50 charged → landlord receives the (agency-branded)
   admin + verification forms → pipeline proceeds exactly as before.
5. Tenants/landlords/property data are editable in-app: property page →
   **Edit records** (the Airtable replacement).

## 6. Data protection notes

- **Isolation**: every operational row carries `agency_id`. The API layer
  scopes every read/write to the signed-in user's agency (verified by the
  smoke test: cross-agency get/update/search all fail), and RLS policies
  mirror the same rule for any future client-side Supabase access.
- **Auth**: Supabase JWTs verified server-side (`SUPABASE_JWT_SECRET`,
  HS256, audience `authenticated`). One agency per user account in v1.
- **RLS**: enabled on all tables; the only policies are member-scoped
  SELECTs — writes happen exclusively through the API.
- Set `ALLOW_BOOTSTRAP_LOGIN=false` in production (kills the shared dev
  account).
- Public landlord forms are scoped by the signed form token (carries
  `agency_id`), so submissions land in the inviting agency only.

## 7. Landing page variations

Three new self-contained drafts in `frontend/design-previews/`
(open `frontend/design-previews/index.html`):

- **D — Aurora Glass**: dark aurora hero, glassmorphism product mock, light sections.
- **E — Bento Dark**: Linear-style dark theme, mono accents, bento feature grid.
- **F — Editorial Mesh**: warm paper, oversized serif, pastel mesh gradients.

All three carry the live pricing (£50 + £5/mo). Pick one and it becomes the
public site / logged-out root.
