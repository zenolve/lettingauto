# Airtable → Supabase migration (+ Stripe scaffold)

This branch (`supabase-stripe-integration`) replaces Airtable as the datastore
with **Supabase (Postgres)** and adds a first-cut **Stripe** payments
integration. The application logic — gate evaluator, handlers PG_00–PG_07,
offer lifecycle, sent-documents, dashboard — is unchanged; only the data layer
was swapped.

## TL;DR — get it running

**Hosted Supabase**

1. Create a project at [supabase.com](https://supabase.com).
2. SQL Editor → paste the whole of [`supabase/migrations/001_init.sql`](../supabase/migrations/001_init.sql) → **Run**.
   (Creates all 28 tables, junctions, indexes, RLS, and seeds the 9 pipeline stages.)
3. Settings → Database → **Connection string** (Session pooler, port 5432) →
   put it in `backend/.env`:

   ```env
   SUPABASE_DB_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```

4. `pip install -r backend/requirements.txt` (new deps: `psycopg[binary,pool]`, `stripe`).
5. Start the backend. Optional but recommended sanity check (creates and
   deletes its own rows):

   ```bash
   cd backend && python -m scripts.smoke_supabase
   ```

**Local development (no Supabase account needed)**

```bash
docker compose -f docker-compose.dev.yml up -d db
# Postgres 16 on localhost:54322, schema auto-applied from supabase/migrations/
# backend/.env already points SUPABASE_DB_URL at it
```

To rebuild the schema from scratch: `docker compose -f docker-compose.dev.yml down -v`.

## Architecture of the swap

The whole codebase accessed Airtable through one facade
(`from app.db import airtable_client as at`). That facade was reimplemented
over Postgres with the **same surface and record shape**, and every import was
flipped to `from app.db import supabase_client as at`:

```
handlers / routers / services       (UNCHANGED logic, still speak
        │                            Airtable field names + record shape)
        ▼
app/db/supabase_client.py           search / find_first / get / create /
        │                           update / delete / all_records / eq / and_ /
        │                           or_ / is_before / first_link / TTL cache
        ▼
app/db/schema.py                    field-name → column registry, link
        │                           junctions, computed lookups
        ▼
Postgres (Supabase)                 supabase/migrations/001_init.sql
```

Records still look like Airtable's wire format —
`{"id": ..., "fields": {...}, "createdTime": ...}` — including the legacy
field-name oddities (`"Annual Rent "` and `"EPC Rating "` with trailing
spaces, `"Gurantor Address"` (sic)). That's deliberate: it keeps the diff to
the 26 consuming modules at exactly one import line each, plus two call sites
that previously built raw Airtable formula strings.

### What changed semantically

| Airtable concept | Supabase equivalent |
|---|---|
| `rec…` record ids | UUIDs (`gen_random_uuid()`); ids remain opaque strings to the app |
| Linked-record fields (symmetric) | One junction table per link pair (`property_landlords`, `offer_properties`, …); the adapter reads/writes both directions, so reverse links (`Properties.Offers`, `Landlords.Properties`) behave exactly as before |
| `Tenants."Property Id"` vs `Properties.Tenant` | **Two separate junctions** (`tenant_property_id`, `property_tenants`) — tenants point at a property from offer creation, the property points back only when an offer is *accepted* (the Gap-5 competing-offers design) |
| Lookup field `Properties.Stage_Order` | Computed at read time from the `property_stage` junction |
| `filterByFormula` strings | Structured builders: `at.eq()`, `at.and_()`, `at.or_()`, `at.is_before()` — compiled to parametrised SQL. `eq(field, False)` matches false **and** unset, like `{f}=FALSE()` did |
| Unset checkbox = absent key | Booleans are real columns defaulting `false`; nulls/empties are omitted from `fields` on read, writing `""` clears a column |
| `multipleCollaborators` (`Stages."Stage agent"`) | `jsonb` list of `{"email", "name"}` objects (seeded empty → agent emails fall back to `ADMIN_EMAIL`) |
| Rate limits / 429 retries | Gone; `with_retry` now only retries transient connection errors |

The per-process TTL read cache (30 s operational / 600 s reference tables) was
kept as-is — it now saves Postgres round-trips instead of Airtable quota, and
writes additionally invalidate the far side of any link they touch.

### Seeded data

* **stages** — the 9 pipeline stages (`Take-on` … `End of Tenancy`). The gate
  evaluator needs these to advance properties. Set `stage_agent` to route
  stage summaries to a specific agent:

  ```sql
  update stages set stage_agent = '[{"email":"agent@palacegate.co.uk","name":"Agent"}]'
  where stage_order = 4;
  ```

* **checklist** — intentionally *not* seeded. The tenant-pack guard requires
  every catalog row to be ticked per property, so an empty catalog means no
  blocking out of the box. Add rows when ready.

### Security (RLS)

Every table has Row Level Security **enabled with no policies**: Supabase's
auto-generated REST/GraphQL APIs are locked for `anon`/`authenticated` keys,
while the backend — connecting directly over `SUPABASE_DB_URL` as the table
owner — bypasses RLS. If you later want client-side Supabase access, add
explicit policies.

### Data migration from the live Airtable base

This branch ships the schema and code, not a data-copy job (the old base
remains untouched on the other branches). If/when you need the historic
records, export each Airtable table to CSV and `insert` into the matching
table, then rebuild the junctions from the link columns. Old `rec…` ids in
`backend/uploads/<id>/…` keep working — the upload routes accept both id
formats.

## Stripe integration (first cut)

New `payments` table + router ([`backend/app/routers/payments.py`](../backend/app/routers/payments.py)):

| Endpoint | Purpose |
|---|---|
| `POST /api/properties/{id}/payments/checkout` | Create a payment row + Stripe Checkout Session (`payment_type`: holding_deposit, deposit, first_month_rent, rent, fee), returns the hosted checkout URL |
| `GET /api/properties/{id}/payments` | List a property's payments |
| `POST /webhook/stripe` | Signature-verified webhook — flips payment status on `checkout.session.completed` / `expired`, `payment_intent.payment_failed`, `charge.refunded` |

Configuration in `backend/.env`:

```env
STRIPE_SECRET_KEY=sk_live_…        # or sk_test_…
STRIPE_WEBHOOK_SECRET=whsec_…      # from the Stripe webhook endpoint config
STRIPE_CURRENCY=gbp
```

Point the Stripe webhook at `https://<your-domain>/webhook/stripe`. With the
keys blank the checkout endpoint returns 501 and the rest of the app is
unaffected. Wiring a succeeded `holding_deposit`/`deposit` payment into the
`funds_cleared` gate flag is the natural next step and intentionally left
manual for now.

## Verification done on this branch

* `pytest` — 62/62 unit tests pass (filter builders, mapping, cache, gate,
  APT, dashboard classification, parsers).
* `python -m scripts.smoke_supabase` against a fresh Postgres — 30 end-to-end
  checks across PG_01 take-on → gate advance → PG_03 offer → acceptance →
  referencing → sent-documents → PG_06 scheduler → payments → cascade delete,
  including reverse-link symmetry and the `Stage_Order` lookup.

## Files of interest

| File | Role |
|---|---|
| `supabase/migrations/001_init.sql` | Complete DDL + seeds (works on hosted Supabase and plain Postgres 14+) |
| `backend/app/db/schema.py` | Airtable-field-name → column/junction registry |
| `backend/app/db/supabase_client.py` | The adapter (CRUD, filters, cache, links, lookups) |
| `backend/app/routers/payments.py` | Stripe checkout + webhook |
| `backend/scripts/smoke_supabase.py` | End-to-end DB smoke test |
| `docker-compose.dev.yml` | Local Postgres with the schema auto-applied |
