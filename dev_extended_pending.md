# dev_extended — pending follow-ups

Things we agreed to defer while doing Wave A of the form-consolidation work
(see the duplicate-field audit on 2026-05-24). Pick these up later in turn.

---

## ✅ Wave B — Residency unification — DONE (2026-05-25)

Shipped on `dev_extended`. `residency` is no longer asked on PG_02b — it's
sourced from the landlord's `UK_Resident_Status` (set by PG_02):
- Model: `LandlordVerificationInput.residency` made `Optional` ([common.py](backend/app/models/common.py))
- Handler: `isOverseas` now derived from `UK_Resident_Status`, falls back to
  payload only if the record lacks a status ([pg02b_verification.py](backend/app/handlers/pg02b_verification.py))
- Form-token endpoint now returns `residency` from the landlord record ([auth.py](backend/app/routers/auth.py))
- Frontend: residency dropdown removed; shown read-only; visa-upload
  conditional now keys off `tokenInfo.residency` ([LandlordVerification.tsx](frontend/src/pages/forms/LandlordVerification.tsx))
- Webhook shim passes `residency` through only as a legacy fallback ([webhooks.py](backend/app/routers/webhooks.py))

_Original plan retained below for reference._

**Duplicate**: `residency` is asked on PG_02 (LandlordAdmin) *and* PG_02b
(LandlordVerification). Identical dropdown (`UK Resident` / `Non-resident
(overseas)`), same landlord, same stage. The PG_02b ask is redundant —
PG_02 always submits first.

**Plan**
1. Backend: drop `residency` from `LandlordVerificationInput` in
   [common.py](backend/app/models/common.py).
2. Backend: in the PG_02b handler, read residency from the Landlord record
   (the `UK_Resident_Status` field PG_02 already writes) instead of the
   payload. Use that to gate any downstream logic (e.g. the visa-snapshot
   conditional).
3. Frontend: drop the "Residency status" field from PG_02b
   ([LandlordVerification.tsx](frontend/src/pages/forms/LandlordVerification.tsx)).
   Replace the `residency?.toLowerCase().includes("non")` conditional that
   currently gates the visa upload — fetch residency from a small endpoint
   (or via the form-token dereference, same pattern as
   `landlord_full_name` in Wave A) and key the conditional off that.
4. Webhooks shim ([webhooks.py](backend/app/routers/webhooks.py)) — drop
   the `residency=` kwarg from the PG_02b construction.

**Risk**: medium. Touches conditional rendering on the verification form
and a Pydantic-required field. Test the non-UK visa-snapshot path
end-to-end after change.

---

## Wave C — Individual vs Company schema alignment

**Schema drift**: PG_02b asks `individual_or_company` and then has a
company-only block (name, reg number, reg address, cert of incorporation,
director name, bank statements). PG_02 has a generic "Full name / Full
address / Mobile" identity block — for a Company landlord, semantics of
"Full name" are ambiguous (company name? director name?).

**Plan** (the biggest of the three; effectively a redesign of stage-2
intake)
1. Lift `individual_or_company` from PG_02b → top of PG_02 (Pydantic
   model + React form).
2. Make PG_02's "Your information" section render differently:
   - **Individual**: keep current fields (Full name, Full address, Post
     code, Mobile, Email).
   - **Company**: Company name, Company reg number, Registered office
     address, Director's name, Director's mobile, Company email.
3. PG_02b becomes purely documentary:
   - ID document upload, visa snapshot (if non-UK)
   - Proof of address upload
   - Proof of ownership upload
   - For Company: cert of incorporation + 3 months bank statements
   - Source of funds + purchase explanation
4. Strip the company text fields (`company_name`, `company_reg_number`,
   `company_reg_address`, `director_name`) from
   `LandlordVerificationInput` once PG_02 carries them.

**Migration consideration**: existing Landlords in Airtable have these
fields populated by PG_02b. New ones will have them from PG_02. No data
migration needed since the column names don't change — just the form
that writes them.

**Risk**: high — restructures the stage-2 flow. Ship behind a feature flag
or do it on a quiet day. Touches both forms, both Pydantic models, both
handlers, and the agent's mental model.

---

## Skipped soft duplicates

### Rename `asking_rent_pcm` → `asking_rent`

**Issue**: the PG_01 field is named `asking_rent_pcm` but the docstring
says it's "value of one rent payment (per frequency)" — i.e. it's a
weekly rent for weekly properties, monthly for monthly. The `_pcm`
suffix is actively misleading.

**Plan**: rename in `PropertyTakeonInput` ([common.py](backend/app/models/common.py))
and the React `FormValues` type + register call in
[PropertyTakeon.tsx](frontend/src/pages/forms/PropertyTakeon.tsx). No
Airtable column rename needed (it's annualised before storage as
`Annual Rent ` per [pg01_takeon.py](backend/app/handlers/pg01_takeon.py)).

**Risk**: low. Pure rename. ~10 minutes.

### Address text vs. address evidence hint (schema clarification)

**Not a duplicate, but landlords occasionally ask why we want their
address twice**: PG_02 captures address text fields; PG_02b asks for a
proof-of-address upload. Different purposes (claim vs. evidence) but the
forms don't explain that.

**Plan**: add a one-line hint to the PG_02b "Proof of address" section:
"This should match the address you gave us on the admin form — it's our
documentary evidence of where you live."

**Risk**: zero. Pure copy change.

### Mobile number only on PG_02

**Not action-required, flagging for awareness**: PG_01 doesn't capture
landlord mobile, only PG_02 does. If Wave C eventually moves identity
collection earlier (e.g. captured on PG_01 by the agent), this is a
field to remember to add there too.

---

## Soft duplicates we agreed to keep as-is (no work needed)

For the record — these are listed so a future audit doesn't re-flag them:

- **`landlord_email`** on PG_01 (typed by agent) + PG_02 (readonly,
  prefilled from token). Already handled correctly — the PG_02 input has
  `readOnly` and a hint explaining why.
- **`asking_rent` (PG_01) vs `monthly_rent` (PG_03)**. Different concepts
  (advertised vs. agreed). Keep separate.
- **NRL approval number** on PG_02 form + landlord flags-catalog PATCH
  endpoint. Two surfaces, same column — sequential edits, not redundant
  input. Keep both.

---

---

## Persistent outstanding-warnings checklist — SUPERSEDED (schema decision still parked)

**2026-05-24 update**: replaced the immediate-need slice of this with a
lightweight read-only `WarningsRecap` panel mounted under the Stage 7
Tenancy Checklist (see [WarningsRecap.tsx](frontend/src/components/ui/WarningsRecap.tsx)
+ `/api/properties/{id}/all-warnings`). That shows every warning ever
raised on the property regardless of dismissal status, with a note
asking the agent to confirm all are addressed before keys are released.
No schema change required — works because PG_05/06/07 don't generate
warnings, so Stage 7 is the natural recap point.

**Known minor gap**: PG_04 is event-driven (DocuSeal webhooks). A
post-Stage-7 decline event would write a new warning that wouldn't be
visible until the agent revisits Stage 7. Rare in practice
(amendments/re-signs).

The full tickable-with-audit version below stays parked. Pick it up
only if the recap proves insufficient.

---

## Move the per-stage document library to Airtable — PARKED (schema decision needed)

**Today**: the "Browse document library" widget that lists pickable
templates per stage is driven by a hardcoded Python list:
[`_CATALOG` in document_library.py](backend/app/services/document_library.py).
~50 entries. Each entry carries:

- `id`, `name`, `stage` (1–9), `default_mode` (sign / email_pdf / email_html)
- `source` (`library_file` or `master_doc`), `body_file` filename
- `signers` (list of roles), `description`
- `tenancy_types` filter (e.g. APT-only docs), `anchor_strings` (DocuSign sig markers)

The actual document bodies are HTML files on disk under
`backend/app/templates/library/` (regenerated by
`scripts/extract_library_docs.py` from `.docx` sources). 

**Note**: this is purely the *catalog of available templates*. The
"documents already sent" history under each stage is already Airtable
(reads `Submissions` table) — no work needed there.

**Why move**: agents can't add a new template or re-classify an
existing one (change its stage, change its default mode, add a tenancy
filter) without a code change + redeploy.

**Schema-change choice** (the decision Asad wants to think through
manually):

| Option | Airtable change | Trade-off |
|---|---|---|
| **A. New `Library_Documents` table; bodies stay on disk** | New table with one row per template. `body_file` column points to the HTML on disk. | Cleanest. Agents can re-classify/add templates from Airtable; legal-contract bodies stay in version control on disk where they belong. The extractor script still owns body refresh. |
| **B. New `Library_Documents` table; bodies move to Airtable long-text** | Same table + a `body_html` long-text column. Drop the disk files. | Agents can edit bodies directly in Airtable. But Airtable's long-text isn't great for 500-line legal contracts; loses git history of body changes; the Tiptap editor on the property page would still be the primary edit surface anyway. |
| **C. Hybrid: catalog in Airtable, bodies on disk, plus an "upload override" Airtable attachment field** | Table with `body_file` + optional `body_override` attachment. | Most flexible but most complex; two sources of truth for the body. |

**Recommendation when you're ready**: **Option A** — table for metadata,
files on disk for bodies. Mirrors how the `Tenancy Checklist` table is
already structured (metadata in Airtable, no body content). Lets agents
re-classify and add new placeholder templates without a deploy. Body
changes still go through the existing `.docx` extractor flow.

**Once decided, work to do**:
1. Schema: create `Library_Documents` table. Columns: `id` (slug),
   `name`, `stage` (number), `default_mode` (singleSelect: sign /
   email_pdf / email_html), `source` (singleSelect: library_file /
   master_doc), `body_file` (text — filename under templates/library/),
   `placeholder_body` (long text — only for `source=master_doc`),
   `signers` (multipleSelect: Landlord / Tenant / Witness),
   `tenancy_types` (multipleSelect: APT / Common Law),
   `anchor_strings` (text — comma-separated), `description`,
   `is_active` (checkbox — to hide without delete).
2. Backend: rewrite `_CATALOG` initialisation in
   `document_library.py` to load from Airtable on import (with a
   process-lifetime in-memory cache; the catalog rarely changes). Keep
   the `LibraryDoc` dataclass shape so call sites don't change.
3. Migration: one-time script to upload the existing 50 entries into
   the new table. Source the data from the current `_CATALOG` list —
   easiest to run the script that builds catalog rows from in-process
   then exits.
4. Frontend: no changes required. `/api/library?stage=N` keeps the same
   response shape.
5. Add a cache-bust endpoint or a periodic refresh — agents editing
   the catalog in Airtable shouldn't need a backend restart to see
   their changes.

**Risk**: low-medium. Pure read-side migration. No data on tenants /
landlords / properties touched. Worst-case rollback: revert the
`document_library.py` change; the table can sit unused.

---

## ✅ Offer-lifecycle handling — ALL GAPS DONE (2026-05-25)

**Shipped on `dev_extended`.** Gaps 1–5 are implemented and the full
lifecycle was verified end-to-end on a throwaway property (create → two
competing Pending offers → accept one [rival auto-Superseded, tenants
linked] → withdraw the accepted one [property rolled back]). New pieces:
- [services/offers.py](backend/app/services/offers.py) — create / accept /
  close, supersede rivals, roll back on close-of-accepted.
- [routers/offers.py](backend/app/routers/offers.py) — list / accept /
  reject / withdraw (Gap 1).
- [pg03_offer.py](backend/app/handlers/pg03_offer.py) — creates an Offer
  row, **no longer overwrites `Properties.Tenant`** (set only on accept).
- [pg04_docuseal.py](backend/app/handlers/pg04_docuseal.py) — offer-letter
  completion → `accept_offer`; decline → `Rejected_By_Landlord`.
- [docusign_client.void_envelope](backend/app/core/docusign_client.py).
- [OffersPanel.tsx](frontend/src/components/ui/OffersPanel.tsx) on Stage 4.
- Migration [scripts/backfill_offers.py](backend/scripts/backfill_offers.py)
  — ran `--apply`, seeded Accepted offers for the 2 existing properties.
- Gap 4 (`Offer_Status`) **folded into** the Offers table's `Status`; no
  separate column built.

_Below: the original gap-by-gap analysis, retained for reference._

**Audit 2026-05-24**: traced what happens when an offer falls through. Today
the system covers the *happy* path well (offer → DocuSign → accepted → TA →
move-in) but has clear gaps for failure modes. Multiple competing offers
on the same property are **not** supported at all.

### Gap 1 — Tenant-record cleanup on landlord/TA decline (small)

When DocuSeal fires a decline event on the Offer Letter or TA
([pg04_docuseal.py:71-99](backend/app/handlers/pg04_docuseal.py)), the
property's `Gate Status` flips to Blocked and the agent is emailed. But:
- `Tenant` link stays on the property
- The DocuSeal envelope isn't voided
- No "Offer_Status: Rejected" state on the Tenant record (no such field)

Agent has no clean way to "this offer is dead, start a new one" — they
have to manually edit Airtable to unlink the tenant.

**Fix sketch**: new endpoint `POST /api/properties/{id}/withdraw-offer`
that unlinks the tenant(s), voids the active DocuSeal envelope (if any),
writes a Submissions audit row with reason free-text, clears
`LL_Offer_Accepted`, re-evaluates the gate. UI button on the property
page (Stage 4 panel, only when an offer is on file). ~2 hours.

**No schema change needed.**

### ✅ Gap 2 — Landlord-silence chase — DONE (2026-05-25)

PG_03 now creates an offer-chase diary entry at `today + 7 days` pinging
the stage agent before the 15-day holding-deposit clock runs out
([pg03_offer.py](backend/app/handlers/pg03_offer.py)). Uses the existing
`Diary_Type="Reminder"` (the singleSelect has no "Offer Chase" option — a
dedicated type would be a one-option schema add). **Bonus fix:** the PG_06
scheduler read `f.get("Type")` (always None) instead of `Diary_Type` — so
*every* diary alert was firing with the generic template and a "Diary
alert: None" subject. Fixed ([pg06_scheduler.py](backend/app/handlers/pg06_scheduler.py)).

_Limitation:_ the chase fires unconditionally at +7d even if the landlord
already signed (it's an internal agent email, harmless). A future tweak
could cancel it when `LL_Offer_Accepted` flips.

### ✅ Gap 3 — Paragon inbound webhook — DONE (2026-05-25)

`POST /webhook/paragon` ([webhooks.py](backend/app/routers/webhooks.py))
ingests `{reference_number, outcome, tenant_email?}`, matches the tenant by
`Referencing_Paragon_Ref` (email fallback), writes `Referencing_Status`
(options match Pass/Conditional/Fail exactly), and re-evaluates the Stage
5→6 gate. `Referencing_Recorded` is set True only for Pass/Conditional — a
**Fail leaves it False so the gate stays blocked** until re-referenced.
Conditional/Fail surface a guarantor-required warning on the Gate_Log.
Optional `PARAGON_WEBHOOK_SECRET` (`?token=`) gate; open in mock mode.

_Note:_ no `Guarantor_Required` column exists, so the guarantor flag is a
warning, not a field. The gate doesn't hard-block on Fail beyond the
Recorded=False mechanism — a deeper "referencing must PASS" gate rule is a
separate design choice.

### Gap 4 — Offer state machine on Tenant (medium, schema change)

Today Tenant has `Referencing_Status` (Pending/Pass/Fail/Conditional)
but no separate `Offer_Status`. Conflates referencing outcome with
offer outcome. A clean model adds:

| Schema change | Detail |
|---|---|
| Add `Tenants.Offer_Status` singleSelect | Options: `Pending`, `Accepted`, `Rejected_By_Landlord`, `Withdrawn_By_Tenant`, `Expired`, `Failed_Referencing` |
| Optionally add `Tenants.Offer_Closed_At` date | When the status moved out of `Pending` |
| Optionally add `Tenants.Offer_Close_Reason` text | Free-text or singleSelect reason |

Decline webhook, withdraw endpoint, and Paragon-fail receiver would
each flip this status to the right terminal value. Lets the dashboard /
Stage 4 panel surface "this property has 3 dead offers and 1 live"
clearly.

**Schema change needed** — Asad to think through whether the existing
`Referencing_Status` should be repurposed or whether a separate
`Offer_Status` is cleaner.

### Gap 5 — Multiple competing offers (large) — ⏳ SCHEMA DONE, logic held

**2026-05-25:** Option A approved. The `Offers` table is **created and
wired** (`tblJLapFX84NYqAPw`, env `AIRTABLE_TABLE_OFFERS`, `TableNames.OFFERS`,
reverse `Offers` links live on Properties + Tenant). 18 fields per the
approved schema (terms snapshotted on the offer; `Status` =
Pending/Accepted/Rejected_By_Landlord/Withdrawn_By_Tenant/Expired/
Failed_Referencing/Superseded). Created by
[scripts/create_offers_table.py](backend/scripts/create_offers_table.py).
**The handler/UI rewrite (steps 2-7 below) is deliberately HELD** per the
user — only the table exists so far. Picking this up later also subsumes
Gap 4's `Offer_Status` intent (don't build Gap 4 separately).

**Today (still the live behaviour until the rewrite lands)**: the
property's `Tenant` link is overwritten on every new offer submission
(see [pg03_offer.py:199-208](backend/app/handlers/pg03_offer.py)).
Orphaned Tenant records from prior offers stay in the table but lose
their `Property Id` back-link. No "offer #2 of 3" concept exists.

**Proposed model — two schema options**:

| Option | Airtable change | Trade-off |
|---|---|---|
| **A. New `Offers` table** | New table: `Property` link, `Tenant(s)` link (multipleRecordLinks), `Status` singleSelect, `Created_At`, `Closed_At`, `Close_Reason`, `Holding_Deposit_Deadline`, `DocuSeal_Envelope_ID`. Property gets `Offers` reverse link. The existing `Properties.Tenant` becomes "the accepted offer's tenants" only — agent UI sets it on acceptance. | Cleanest. First-class "offer" concept. Easy to render a competing-offers panel. Audit trail of every attempt with reason. |
| **B. Stay on Tenant, add `Offer_Status`** | Just the Gap-4 fields. `Properties.Tenant` becomes a multipleRecordLinks holding *every tenant ever offered*, with statuses on each. Agent's "accepted offer" view filters by `Offer_Status=Accepted`. | Half a schema change but conflates two concepts in one table. Joint-applicant relationships ("these two tenants are on the same offer") become awkward — you'd need an `Offer_Group_ID` text field to associate them. |

**Recommendation**: **Option A** when ready. The audit-trail value of
a real `Offers` table is substantial; HMO joint-applicant grouping is
naturally one row with a multi-tenant link.

**Once decided, work to do**:
1. Schema: create the table + reverse link.
2. Backend: rewrite `handle_offer` to create an Offer row (with
   linked Tenant(s)), leave `Properties.Tenant` empty until acceptance.
3. PG_04 decline webhook: flip `Offers.Status=Rejected_By_Landlord`
   instead of leaving things dangling.
4. New `POST /api/offers/{id}/accept` — copies tenant(s) to
   `Properties.Tenant`, sets other competing offers to
   `Rejected_By_Landlord` (or `Closed_Other_Accepted`), advances gate.
5. New `POST /api/offers/{id}/withdraw` — sets `Withdrawn_By_Tenant`,
   voids envelope.
6. Frontend: Stage 4 panel rewritten as an offers list with per-row
   accept/reject/withdraw. Existing Offer.tsx form becomes "add an
   offer", not "set the offer".
7. Migration: existing `Properties.Tenant` data → seed Offers table
   with `Status=Accepted` for any property currently at stage 5+.

**Risk**: high — touches the entire offer-stage data flow + UI.
Definitely a deliberate-decision project, not a side quest.

---

## Outstanding warnings — full per-item resolution model (Parked alternative)

> This is the deeper version of the SUPERSEDED entry above. The lightweight
> `WarningsRecap` panel already addresses the immediate concern; pick this
> up only if the recap proves insufficient.

**Problem raised 2026-05-24**: warnings generated at one stage (e.g.
PG_02 compliance findings) can be forgotten once the agent moves
forward. Today they:
- Live as a multi-line text blob on `Gate_Log.Gate Warnings`
- Surface as a single banner via `ReviewPanel` → `/latest-review`
  (most-recent non-dismissed row with warnings)
- Get hidden as an all-or-nothing batch when the agent clicks "Dismiss"

Code-wise the warnings DO persist across stage advances (the endpoint
walks every linked Gate_Log row, not just the current stage's). But
once dismissed, they're gone — and the multi-line-text representation
makes per-item resolution impossible.

**Proposed model** (mirroring the existing Stage 7 Tenancy Checklist):
a persistent checklist of outstanding warning items the agent ticks off
one at a time. Each item carries source stage, source submission, raw
warning text, resolved-by, resolved-at. Survives stage advances.

**Schema-change choice** (the decision Asad wants to think through
manually):

| Option | Airtable change | Trade-off |
|---|---|---|
| **A. New `Outstanding_Items` table** | **New table** (Name, Property link, Source, Stage_Generated, Created_At, Resolved, Resolved_By, Resolved_At) + new `Properties.Outstanding_Items` reverse link | Cleanest separation. System-generated items don't pollute the human-curated `Tenancy Checklist`. Each warning is a real record with audit fields. |
| **B. Reuse existing `Tenancy Checklist` table** | **One new field** on `Tenancy Checklist`: `Auto_Generated: bool` (plus optionally `Source_Stage`, `Source_Gate_Log` link) | No new table. But every consumer of the catalog now needs to filter (`is_template` AND NOT `auto_generated` for the static picker; `auto_generated AND linked-to-this-property` for the warnings panel). Conflates two different lifecycles. |
| **C. Split `Gate Warnings` text → linked rows** | New table (effectively the same as Option A) + writer changes in `pg00_gate._write_gate_log` to create one row per warning instead of writing a multi-line string | Same schema effort as A. Bonus: Gate_Log stays a clean audit table; warnings get first-class status. Backwards-compat: would need a migration to convert existing multi-line text into rows, or accept that history is read-only. |

**Recommendation when you're ready**: **Option A** is the cleanest. The
existing Tenancy Checklist catalog should stay human-curated. A new
table is ~5 columns and a single link field on Properties — small but
deliberate.

**Once decided, work to do**:
1. Schema: create the table + reverse link in Airtable.
2. Backend: in `pg00_gate._write_gate_log` (or directly in
   `pg02_admin`/wherever warnings are generated), create one
   `Outstanding_Items` row per warning instead of (or alongside) the
   `Gate Warnings` text blob.
3. Backend: new endpoints `GET /api/properties/{id}/outstanding-items`,
   `POST /api/properties/{id}/outstanding-items/{item_id}/resolve`
   (mirrors the existing checklist pattern in
   [checklist.py](backend/app/routers/checklist.py)).
4. Frontend: new `OutstandingItemsPanel` component, replaces (or sits
   above) `ReviewPanel`. Items rendered as tickable rows with source
   stage + date; resolving an item flips `Resolved_*`. The "Dismiss"
   button on the current ReviewPanel goes away — bulk dismissal is no
   longer the model.
5. Migration: existing `Gate_Log.Gate Warnings` text blobs stay on the
   audit row for history but are not the source of truth for the
   panel. Optionally one-time-migrate active blobs → Outstanding_Items
   rows so the existing batch is preserved.
6. Decide: do we keep `Gate Warnings` writes too (for the audit row)
   or stop populating it once the new system lives?

**Risk**: medium — touches data model + every place that writes
warnings. Schema migration is the gate (literally).

---

## Dashboard — Phase 2 / 3 follow-ups (Phase 1 shipped 2026-06-01)

**Phase 1 is DONE** on `dev_extended`: `GET /api/dashboard` aggregation
endpoint ([dashboard.py](backend/app/routers/dashboard.py)) + new
entry-point [Dashboard.tsx](frontend/src/pages/Dashboard.tsx) (act-now
cards, pipeline stage bars, compliance donut, cert runway, diary agenda,
stalled deals, portfolio splits, offer conversion). Property list moved to
[Properties.tsx](frontend/src/pages/Properties.tsx) at `/agent/properties`.
Pure classifier unit-tested ([test_dashboard.py](backend/tests/test_dashboard.py)).

### Phase 1.5 — URL-filtered drill-downs (small, no schema)
Act-now cards and stage bars currently link to the unfiltered
`/agent/properties` list. Make them deep-link to a pre-filtered view, e.g.
`/agent/properties?gate=blocked`, `?stage=7`, `?expiring=30`. Needs:
- `Properties.tsx` to read query params and filter client-side (data's
  already on the page).
- Dashboard links to pass the right param.
~2 hours. High UX payoff — closes the loop from "12 blocked" → the actual 12.

### Phase 2 — trends over time (needs a history source)
The current dashboard is a point-in-time snapshot. Trend lines need history:
- **Take-ons per month** — derivable now from `Properties.createdTime`
  (group by month). No new storage. Line/bar sparkline.
- **Rent-roll growth** — needs periodic snapshots (rent roll today tells you
  nothing about last month). Add a tiny `Metrics_Snapshot` table or a daily
  cron row, **or** approximate from tenancy start dates.
- **Avg time-to-let** (take-on → move-in) — derivable from `Gate_Log`
  timestamps (first stage-1 row → first stage-8 row per property), or from
  `Stage changed at` history if we start logging it. Stat + trend.
- **Offer conversion rate over time** — from `Offers.Created At` / `Closed At`.

**Decision needed:** rent-roll/portfolio trends want a snapshot table
(schema add) — park until Phase 2 is greenlit. Take-ons + time-to-let need
no schema (derive from existing timestamps).

### Phase 3 — polish / nice-to-have
- **Activity feed** — recent `Gate_Log` + `Submissions` + `Offers` events as
  a timeline ("Offer accepted — 24 Onslow", "11 Palace Gate → Stage 6").
  Low effort, high "alive" value. No schema.
- **Per-agent views** — filter the dashboard to the logged-in agent's
  properties (needs a reliable "Stage agent"/owner field per property —
  currently `Stage agent` lives on the Stages table, not per property).
- **Targets / goals** — gauge/bullet charts vs a target (e.g. lets this
  quarter). Needs a place to store targets (small schema or config).
- **Gauges** for compliance % vs 100%.

### Known data gaps that make some metrics hollow until fixed
- **Rent roll** uses `Properties."Annual Rent "` (asking rent at take-on),
  not the accepted offer's agreed rent. For accuracy, source from the
  accepted `Offers.Offered Rent` / `Tenant.Amount`. Also requires Annual
  Rent to actually be populated.
- **Financials table is largely unwired** — so disbursement / commission /
  arrears metrics can't be shown yet. Wire `Financials` first.
- **EPC has no expiry field** in the base (only rating + status), so the
  cert runway covers Gas + EICR only. Add `EPC Expiry` if EPC renewal
  tracking is wanted (schema add).

---

## ✅ In-memory Airtable caching — DONE (2026-06-01)

Shipped on `dev_extended`. Read-through TTL cache in
[airtable_client.py](backend/app/db/airtable_client.py) (`_TTLCache`,
thread-safe): `get`/`all_records`/`search`/`find_first` are cached,
`create`/`update` bust the whole table's entries. Tiered TTLs — Stages /
Tenancy Checklist 10 min, everything else 30 s. `fresh=True` bypass on all
reads; the re-evaluate-gate endpoint calls `invalidate(PROPERTIES)` +
`invalidate(TENANTS)` first so out-of-band edits surface instantly. The
whole dashboard result is also cached 30 s (`?fresh=1` bypasses). Disabled
under `APP_ENV=test` for deterministic tests; unit-tested
([test_cache.py](backend/tests/test_cache.py)) + live-verified
(read-through hit, invalidation refetch, dashboard snapshot, fresh bypass).
**Redis is still the upgrade path** once multiple workers are in play (note
left in the client). _Original plan retained below._

**Why**: we're at risk of the Airtable monthly API-request cap. Reads
dominate — the dashboard (now the entry point) reads 4 full tables per
load, `find_stage_by_order(Stages)` fires on every gate evaluation, and
the property list re-reads all Properties on every visit.

**Where**: wrap the read functions in
[airtable_client.py](backend/app/db/airtable_client.py) — the single choke
point (its docstring already anticipates "one place to add … caching").
`get` / `all_records` / `search` / `find_first` become read-through; `create`
/ `update` bust the cache. Zero changes for callers.

**Strategy — read-through TTL cache + write-invalidation, tiered TTLs:**

| Tier | Tables | TTL | Rationale |
|---|---|---|---|
| Reference / near-static | `Stages`, `Tenancy Checklist` | 5–10 min | `find_stage_by_order` runs on every gate transition; almost never changes — biggest hidden cost |
| Operational | Properties, Tenant, Offers, Diary, Landlords, Gate_Log, Compliance, Financials | 30–60 s | Dashboard + lists reread constantly; short TTL keeps direct-Airtable edits surfacing fast |

**Mechanics:**
- Key = `(op, table, normalized-args)` e.g. `("all","properties",None)`,
  `("get","tenants","rec123")`, `("search","offers",'{Status}="Pending"')`.
- Thread-safe: FastAPI runs sync endpoints in a threadpool → a
  `threading.Lock` around a small TTL dict (~30–40 lines, **no new
  dependency**). `cachetools.TTLCache` is the alternative.
- **Invalidation**: on any `create`/`update` to a table, bust *that whole
  table's* cache entries (coarse but correct — a write can change any
  `all_records`/`search` result, not just one record). Writes are rare vs
  reads, so this is cheap.

**Critical caveat for this app — the re-evaluate-gate workflow:**
the system deliberately supports editing Airtable directly then hitting
"Re-evaluate gate." Caching must not break that:
1. Keep operational TTL short (30–60 s) so out-of-band edits surface fast.
2. Add a `fresh=True` bypass on the read functions and call it from the
   re-evaluate endpoints (`POST /api/properties/{id}/reevaluate-gate` and
   the gate eval it triggers) so "fixed it in Airtable → re-evaluate" is
   instant, not up to 60 s stale.

**Apply first (biggest savings):**
1. `Stages` (long TTL) — called on every transition; likely the #1 cost.
2. Dashboard's 4 `all_records` — entry point, every nav = 4 calls; 30 s TTL
   collapses to 4 calls per 30 s window. (Optional: also cache the computed
   `_build_dashboard()` result ~30 s = 1 entry instead of 4.)
3. Property-list `all_records(PROPERTIES)` + property-detail per-record `get`s.

**⚠ Redis / multi-worker limitation (important):**
An in-memory cache is **per-process**. It's fine today because uvicorn runs
a single process (`python -m uvicorn app.main:app`, no `--workers`). The
moment we run **multiple workers/processes** (`--workers N`, gunicorn, or
horizontal scaling), each worker keeps its own cache → N× the misses **and**
cross-worker inconsistency (a write busts only the serving worker's cache;
the others stay stale until TTL). At that point move to a **shared Redis
cache** (same read-through + invalidation pattern, just backed by Redis so
all workers share state and invalidation is global). Leave a one-line
comment in `airtable_client.py` noting this so it isn't a surprise later.
Also note: caching only cuts **reads** — writes still cost API calls (but
reads dominate here).

**Risk**: low. Pure read-path optimisation behind the existing client
surface; TTL bounds staleness; the `fresh=` bypass protects the one
workflow that needs real-time reads.

---

## ✅ Record documents sent per stage — `Sent_Documents` table — DONE (2026-06-02)

Shipped on `dev_extended`. Table created (`tblyG0gijqAN5bo5x`, 13 fields,
reverse link `Properties.Sent_Documents`) +
[create_sent_documents_table.py](backend/scripts/create_sent_documents_table.py),
wired into config/TableNames/.env. New service
[sent_documents.py](backend/app/services/sent_documents.py)
(`record_sent` / `update_status_by_envelope` / `list_for_property`).
Writers: library send ([library.py](backend/app/routers/library.py) — the
`Submissions` "Library:" hack is **removed**; `/sent` reads the new table),
PG_03 offer letter, PG_05 prescribed pack (Channel=Attachment). PG_04 webhook
flips `Status` → Signed/Declined by `Envelope ID`. Frontend shows a status
badge + "attachment" channel. No backfill (per decision). Live-verified:
record → list → status-flip → cleanup. `Submissions` is now form-submissions
only. _Original proposal below._

## (proposal) Record documents sent per stage — `Sent_Documents` table

**Problem.** "What documents have been sent at each stage" is currently
recorded by overloading other tables, fragilely:
- Library editor sends write a `Submissions` row with `Form Name =
  "Library: {name} ({mode})"` and a **python-repr JSON string** in
  `JSON Data` (parsed back with `ast.literal_eval` —
  [library.py](backend/app/routers/library.py)).
- The **stage is derived** from the catalog at read time, not stored (breaks
  if the catalog changes; can't be queried).
- The library send row **doesn't even set `Submitted Date`**, so the "sent"
  list sorts on a mostly-null field.
- **Signing status is never reflected** on the sent record — only on Property
  flags. You can't see "this offer letter was sent, then signed/declined".
- Prescribed-pack docs (PG_05) go to a **different** table (`Compliance`), so
  there's no single "everything sent for this property" view.

**Proposed schema — new `Sent_Documents` table** (one row per document send):

| # | Field | Type | Notes |
|---|---|---|---|
| 1 | **Name** | singleLineText (primary) | `"{Doc Name} · {address} · {date}"`, set by writer |
| 2 | **Property** | link → Properties | auto-creates reverse `Sent_Documents` on Properties |
| 3 | **Doc ID** | singleLineText | catalog slug (`tpl_05`, `apt_pet_abnb`, `served_gas_cert`) |
| 4 | **Doc Name** | singleLineText | human label |
| 5 | **Stage** | number | 1–9, **stored** (not derived) |
| 6 | **Channel** | singleSelect | `Sign` / `Email PDF` / `Email HTML` / `Attachment` (prescribed pack) |
| 7 | **Recipients** | singleLineText | comma-separated emails |
| 8 | **Sent Date** | date | actually set this time |
| 9 | **Sent By** | singleLineText | agent email, or `system` for auto sends |
| 10 | **PDF URL** | text | stored PDF (sign / email_pdf modes) |
| 11 | **Envelope ID** | singleLineText | DocuSign/DocuSeal id — links status updates back |
| 12 | **Status** | singleSelect | `Sent` / `Delivered` / `Viewed` / `Signed` / `Declined` / `Voided` |
| 13 | **Completed Date** | date | when signed/declined |

**Writers (after the table lands — implementation, not part of the schema
approval):**
- `library.py` send endpoint → write a `Sent_Documents` row (replaces the
  `Submissions` "Library:" hack; `/sent` endpoint reads this table instead).
- PG_05 prescribed-docs → write rows with `Channel = Attachment` (so the pack
  shows up in the same per-stage view).
- PG_03 offer letter / PG_04 contract sends → write rows.
- **PG_04 webhook → UPDATE the matching row's `Status` + `Completed Date`** by
  `Envelope ID` when an envelope completes/declines (envelope id is already
  persisted as of the earlier library change — this closes the loop).

**Migration:** one-time backfill of existing `Submissions` "Library:" rows →
`Sent_Documents`, or leave them as historical (decide at build time).

**Risk:** low–medium. New table + reverse link only; existing rows untouched
until migration. Biggest payoff: a real per-stage sent-document audit with
live signing status.

**⚠ Needs your approval on the schema before I create the table** (new
`Sent_Documents` table + the reverse link on Properties; no changes to
existing fields).

---

## ✅ TPL prepopulation — DONE (2026-06-02, on dev_extended_v2)

Shipped. Expanded [merge_fields.py](backend/app/services/merge_fields.py)
build_merge_context to **54 keys** sourced from real Properties / Landlords /
Tenant fields (verified against live schema; **fixed a latent bug** — property
postcode read `"Post Code"` but the field is `post_code`, so it was always
blank). Added an **offer-fallback** so offer-stage letters prepopulate from
the latest offer's tenant before acceptance. Authored **44 TPL bodies**
(TPL-01..42 + 35a/b/c) as real letters with `{{merge}}` tokens where data maps
and `[bracketed]` blanks where not, via
[author_tpls.py](backend/scripts/author_tpls.py) → `templates/library/tpl_*.html`.
All 44 promote to `library_file`; verified zero unknown tokens, sample renders
with only intended manual blanks.

**Still pending (the "big contracts", left for last as agreed):** embed merge
tokens into `pg_tcs_2026` (T&C), `apt_pet_abnb` (APT TA), `common_law_ta`
(Common Law TA). Also: a few merge values have no Airtable field yet and stay
manual everywhere — deposit scheme name + cert ref, commission rate, arrears
amounts, maintenance/works detail, contractor details.

---

_Generated 2026-05-24 while landing Wave A on `dev_extended`. Updated
2026-06-01 with dashboard Phase 2/3 follow-ups, the Airtable caching plan,
and the Sent_Documents schema proposal; 2026-06-02 with TPL prepopulation._
