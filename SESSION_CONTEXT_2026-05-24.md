# Palace Gate Lettings — session handoff 2026-05-24

Continuation brief for the next Claude session. Read this top-to-bottom before
touching anything; it's the shortest path back to the mental model.

---

## 1. What this is

**Palace Gate Lettings** — a property letting workflow system replacing a
Tally + n8n + Airtable pipeline. Built across this multi-session collaboration.

**Stack**
- Backend: FastAPI (Python 3.11), Pydantic v2, pyairtable
- Frontend: React 18 + Vite + TypeScript + Tailwind + Tiptap + axios + react-router-dom v6
- DB: Airtable (base `appgqHgbJut9LYksm`)
- Signing: DocuSign (JWT bearer) in `dev`/`production`, mock in `test`
- PDF: Playwright/Chromium (subprocess) → WeasyPrint → fpdf2 fallback chain
- Email: SMTP via aiosmtplib

**Repo root**: `C:\Users\asadn\Documents\ZENOLVE\lettingauto`
- Backend: `backend/`
- Frontend: `frontend/`
- Git: branch `dev`, single committed snapshot (no `master`/`main` yet).
  All later work since the initial commit is uncommitted on `dev`.

---

## 2. Where we are at the end of this session

### 9-stage workflow model

| Stage | Name | Form / source | Gate-blocking fields |
|---|---|---|---|
| 1 | Take-on | PG_01 (`/agent/properties/new`) | Landlords linked (auto) |
| 2 | Compliance | PG_02 admin form | Gas/EPC/EICR status, EPC ≥ E, expiry dates, `TC_Signed` |
| 3 | Marketing | (FileUploader photos/floor_plan) | `TC_Signed` |
| 4 | Offer | PG_03 (`/agent/properties/:id/offer`) | `LL_Offer_Accepted`, `Anti_Discrimination_Confirmed` (APT), `HMO_Licence_Confirmed` |
| 5 | Referencing | ReferencingPanel | `Referencing_Recorded` per tenant, `LL_Offer_Accepted` |
| 6 | TA Signing | Library → TA + DocuSign | `TA_LL_Signed`, `TA_TT_Signed`, `TDS Cert On File`, `Deposit Registered` |
| 7 | Pre Move-in | TenancyChecklist + Move-in form | `funds_cleared`, `Works_Signed_Off`, served flags |
| 8 | Live Tenancy | DiaryCard + library at-tenancy docs | (no gate) |
| 9 | End of Tenancy | Library docs | (no gate) |

Gate logic lives in [pg00_gate.py](backend/app/handlers/pg00_gate.py) `TRANSITIONS` map.

### What's UI-managed now (end-to-end lifecycle)

**Every gate-blocking field has a UI toggle.** Either:
- A form submission sets it (PG_02 etc.)
- A DocuSign webhook sets it (TC_Signed, TA_LL_Signed, TA_TT_Signed)
- An explicit manual toggle (the PATCH /flags endpoint)
- A manual override toggle (with confirmation modal — signing flags)

Backend allowlist: [`PATCHABLE_FLAGS` in properties.py](backend/app/routers/properties.py).
14 patchable fields including all signing overrides + served flags + AML +
Westminster + Inventory_Clerk.

### What's NOT in the UI (deliberate gaps for Wave 2 / 3)

- **RTR (Right to Rent)** — Pydantic model accepts the fields but the React
  Offer form doesn't expose them; Airtable singleSelect for `RTR_Check_Type`
  is `[Manual, Paragon, Online Home Office]` but Pydantic accepts
  `[Manual, IDSP, Share Code, Paragon]` — mismatch will 422 if `IDSP` or
  `Share Code` is ever submitted. **Wave 2** scope.
- **Financials** table — `Deposit_Received`, `First_Rent_Cleared`,
  `TDS_Registered`, `Disbursement_Approved` etc. have no UI at all.
  **Wave 3** scope.
- **Per-tenant** `Standing_Order_Confirmed`, `Pet_Request_Received`, `Pet_Request_Date`,
  `Ground_4A_Notice_Served_Date` — fields exist, no UI. Wave 3.
- **End-of-tenancy** `Checkout_Date`, deposit return flow, archive — not
  modelled. Wave 3.
- **Form 4A** (S13 rent-review notice) — diary alert fires at month 9.5
  (`E11_rent_review.html`) but no library document. User asked to leave for
  now. PDF in `~/Downloads/Form_4A_Latest.pdf` if we want to wire it up.

---

## 3. Recent work (this session, 2026-05-23 → 24)

### Wave 1: manual flag panels (DONE, live-verified)

New backend endpoint `PATCH /api/properties/{id}/flags` + `GET /flags-catalog`.
14 allowlisted fields with type metadata (`bool` / `bool_with_date` / `text`).
`bool_with_date` auto-stamps the paired date column on tick, clears on untick.
Unknown fields → 400. Doesn't re-evaluate the gate or email — quiet writes.

Frontend `<PropertyFlags>` component renders the right widget per type;
optimistic UI; reverts on error.

Wired into PropertyDetail stages 4 / 6 / 7 / 8.

### Secondary gaps fill (DONE)

- **Signing overrides**: TC_Signed, TA_LL_Signed, TA_TT_Signed now in
  PATCHABLE_FLAGS with `confirm` metadata (warning tone, body text about
  bypassing DocuSign audit trail).
- **Landlord-level flags**: new [`/api/landlords/...`](backend/app/routers/landlords.py)
  router. `GET /flags-catalog` + `PATCH /{id}/flags`. Handles
  `Verification Status` (single_select Pending Review/Approved/Rejected),
  `ID_Name_Match` (single_select Pending/Confirmed/Mismatch),
  `NRL_Approval_Number` (text). When ID_Name_Match flips off Pending,
  AML_Check_Date + AML_Checked_By auto-stamp.

### Modal infrastructure (DONE)

[`<ConfirmDialogProvider>` + `useConfirm()` hook](frontend/src/components/ui/ConfirmDialog.tsx).
Mounted in AgentLayout. Returns `Promise<boolean>` so callers `await` inline.
Three tones: info / warning / danger. Esc closes; backdrop click cancels;
focus traps cancel button. **Reusable across the app — drop `confirm` block
on any catalog entry to gate it.**

PropertyFlags generalised: accepts `entityId` + `catalogPath` + `patchPath`
(legacy `propertyId` kept as alias). Added `single_select` widget. Auto-
invokes useConfirm when catalog declares a confirm block; only on
"consequential" direction (ticking bool, any value change for select/text —
NOT unticking).

### Wired into PropertyDetail (DONE)

- **Stage 2**: LandlordFlags card (Verification, ID match, NRL)
- **Stage 3**: TC_Signed override + Westminster_Licence_Number
- **Stage 4**: Anti_Discrim + HMO_Licence (when HMO_Flag)
- **Stage 6**: TA_LL_Signed + TA_TT_Signed overrides (separate card from TDS/Deposit)
- **Stage 7**: funds_cleared + Works_Signed_Off + Inventory_Clerk
- **Stage 8**: served flags manual override (How To Rent, Gas, EPC, EICR, TDS Info, RRA-APT)

### Document extraction overhaul (DONE)

Old hand-rolled XML walker dropped numbered lists + paragraph styles, so the
contracts rendered as walls of `<p>`. Replaced with **mammoth** + style map:
- Maps `Heading1/Title/Boldsubheading/Untitledsubclause*/Schedule/Testimonium`
  to semantic HTML
- Preserves `w:numId` numbered lists, bullets, tables, bold runs

[extract_library_docs.py](backend/scripts/extract_library_docs.py) rewritten.

APT TA went from 0 `<h1>` / 0 `<ol>` to **7 / 64** (plus 9 bullets, 14 tables).
T&C 2026 re-extracted too with proper structure; **`/sig1/`, `/sig2/`,
`/pg_sig1/` markers manually restored** after re-extraction wiped them.

### Re-evaluate gate (DONE)

Airtable edits don't trip our gate code → cached `Gate Status` /
`Gate Block Reason` go stale.

- Backend: `evaluate_gate(..., silent=True)` skips agent emails (Gate_Log
  still written). New endpoint `POST /api/properties/{id}/reevaluate-gate`
  derives current stage from fields, runs gate against current+1 silent.
- Frontend: `<GateStatusBar>` component wraps the rose "Blocked" panel +
  adds a "Re-evaluate gate" button. Also shows a ghost button when unblocked
  so agents can re-check at will.

**Live-tested on `recG3FO5MPtPbGOyC` (11 Palace Gate)**: cleared stale
"EICR expired" message that referenced a date 3 months old; now correctly
reports the actual current blockers at stage 5 (LL_Offer_Accepted +
Anti_Discrimination_Confirmed).

### Common Law TA — needs user action

It's a `.doc` (legacy binary), mammoth doesn't read it; antiword fallback
produces broken output. User needs to:
1. Open `Tenancy Agreement Common Law December 2020 (1).doc` in Word
2. **File → Save As → .docx** (same name, same Downloads folder)
3. Run `python -m scripts.extract_library_docs` from `backend/`

The extractor's `SOURCE_FILES` is already pointing at the .docx name.

### Form 4A

User attached the PDF (`~/Downloads/Form_4A_Latest.pdf`) but said leave it
unless we already handled it. We don't ship it as a library doc (only a diary
reminder fires for S13 rent reviews). Not adding for now.

---

## 4. File map — what to read first

### Backend essentials
- [pg00_gate.py](backend/app/handlers/pg00_gate.py) — `TRANSITIONS` map of every gate condition
- [properties.py](backend/app/routers/properties.py) — flags catalog + PATCH endpoint + reevaluate-gate + property CRUD
- [landlords.py](backend/app/routers/landlords.py) — landlord flags catalog + PATCH (single_select handling)
- [signing.py](backend/app/core/signing.py) — DocuSign/mock dispatcher
- [docusign_client.py](backend/app/core/docusign_client.py) — JWT bearer + envelope create
- [pre_signatures.py](backend/app/services/pre_signatures.py) — `/pg_sigN/` registry + substitute
- [pdf_renderer.py](backend/app/core/pdf_renderer.py) — render chain (Chromium subprocess → WeasyPrint → fpdf2)
- [_chromium_worker.py](backend/app/core/_chromium_worker.py) — standalone Playwright runner (subprocess-isolated so Windows SelectorEventLoop doesn't block it)
- [document_library.py](backend/app/services/document_library.py) — library catalog
- [compliance.py](backend/app/services/compliance.py) — PG_02 warning/action engine

### Frontend essentials
- [PropertyDetail.tsx](frontend/src/pages/PropertyDetail.tsx) — all 9 stage panels, GateStatusBar, ReviewPanel mounting
- [PropertyFlags.tsx](frontend/src/components/ui/PropertyFlags.tsx) — generalised flag editor (bool / bool_with_date / single_select / text + confirm)
- [ConfirmDialog.tsx](frontend/src/components/ui/ConfirmDialog.tsx) — modal provider + useConfirm hook
- [LibraryEditor.tsx](frontend/src/pages/LibraryEditor.tsx) — Tiptap + signature dropdown + preview/download/send
- [Signatures.tsx](frontend/src/pages/Signatures.tsx) — admin page for signatory registry (draw/upload)
- [ReviewPanel.tsx](frontend/src/components/ui/ReviewPanel.tsx) — surfaces latest non-dismissed Gate_Log warnings/actions
- [ReferencingPanel.tsx](frontend/src/components/ui/ReferencingPanel.tsx) — per-tenant Paragon UI

### Forms (React, all at `/agent/properties/...`)
- [PropertyTakeon.tsx](frontend/src/pages/forms/PropertyTakeon.tsx) — PG_01
- [LandlordAdmin.tsx](frontend/src/pages/forms/LandlordAdmin.tsx) — PG_02 (Tally-parity, 90+ fields)
- [LandlordVerification.tsx](frontend/src/pages/forms/LandlordVerification.tsx) — PG_02b
- [Offer.tsx](frontend/src/pages/forms/Offer.tsx) — PG_03
- [MoveIn.tsx](frontend/src/pages/forms/MoveIn.tsx) — PG_05 tenant pack trigger

---

## 5. Env vars

`backend/.env` (NOT in git):
```
JWT_SECRET=<...>
AGENT_BOOTSTRAP_EMAIL=admin@palacegate.com
AGENT_BOOTSTRAP_PASSWORD=<...>

AIRTABLE_TOKEN=<...>
AIRTABLE_BASE_ID=appgqHgbJut9LYksm
AIRTABLE_TABLE_PROPERTIES=tblbzHoCEe06wxe24
AIRTABLE_TABLE_LANDLORDS=tblVIXNIkrRp9Xxh2
AIRTABLE_TABLE_TENANTS=tblEHjL5hgAsO3Bp7
AIRTABLE_TABLE_DIARY=tblE9U8jtmI3DTHbJ
AIRTABLE_TABLE_FINANCIALS=tblj71Zu2Jn260nY0
AIRTABLE_TABLE_CHECKLIST=tblGiQey64sUuIp2j
AIRTABLE_TABLE_SUBMISSIONS=tblaflLP7VFCoPMJo
AIRTABLE_TABLE_STAGES=tblIHHIgbF7WbL4bt
AIRTABLE_TABLE_GATE_LOG=tbljoHc7WkcRalZPS
AIRTABLE_TABLE_COMPLIANCE=tblr59bPp9oUusMgJ

APP_ENV=dev                                # dev/production → DocuSign; test → mock
DOCUSIGN_INTEGRATION_KEY=81f5bc08-f001-420b-a577-8da325f593ff
DOCUSIGN_USER_ID=<...>
DOCUSIGN_ACCOUNT_ID=9b3b5b09-42a3-4547-a8b1-8370c7c11c7c
DOCUSIGN_PRIVATE_KEY_PATH=docusign_rsa.key  # relative to backend/ — gitignored
DOCUSIGN_AUTH_SERVER=account-d.docusign.com
DOCUSIGN_BASE_PATH=https://demo.docusign.net
DOCUSIGN_CONNECT_HMAC_SECRET=<...>          # generated in DocuSign Connect Keys tab
```

**Note** — the user's .env has `DOCUSIGN_AUTH_SERVER =...` with a space before
`=`. python-dotenv tolerates it, but other tools won't. Cosmetic fix when
convenient.

**Consent grant**: one-time, already done. The URL was:
```
https://account-d.docusign.com/oauth/auth?response_type=code&scope=signature%20impersonation&client_id=81f5bc08-f001-420b-a577-8da325f593ff&redirect_uri=https://www.docusign.com
```
If consent ever revokes, the JWT exchange returns a structured error that
re-surfaces this URL.

**DocuSign Connect**: configured to POST to `<ngrok>/webhook/docusign` with
HMAC signing on. Free ngrok URL changes on restart — update the Connect URL
each time. Manual fallback: `POST /webhook/docusign/poll/{envelope_id}`.

---

## 6. Test property + record IDs

Useful for live testing without creating new ones:

| ID | Address | Purpose |
|---|---|---|
| `recG3FO5MPtPbGOyC` | 11 Palace Gate | Real-ish property, used for the gate-reevaluate fix |
| `recPqAemV5Bx5Ms3b` | 1 Demo Review Lane | The "default" smoke-test property |
| `reckbfBxU9fE3WXrL` | 2 Audit Lane (audit suffix) | Had a fake gas cert PNG seeded for move-in pack tests |
| `recRh2jSnbwJDPj9R` | Warning-test property | Heavy use during PG_02 warnings verification |
| Various "Audit/Warning/Final" properties | — | Litter from earlier smoke tests; delete in Airtable when convenient |

Property `recG3FO5MPtPbGOyC` was tested with reevaluate-gate today and
correctly surfaced its real blockers (anti-discrim + LL_Offer_Accepted).

---

## 7. Outstanding work — pick-up list

### Immediate (small)
1. **User must save Common Law `.doc` → `.docx`** then re-run extractor.
   Code is ready, file format isn't.
2. **`.env` cosmetic**: spaces before `=` on two DOCUSIGN_* lines — leave or fix.
3. **Test artifacts**: 5-10 stale properties in Airtable from smoke tests.
   Worth a bulk-delete pass when bored.

### Wave 2 (RTR) — designed, not started
- Add `[Manual | Paragon | Online Home Office]` to Pydantic `RTRCheckType`
  (drop IDSP / Share Code unless those Airtable options get added too)
- Add RTR section to React Offer form (per-tenant + per-co-tenant)
- Add Tenant table columns `Passport_URL`, `Visa_URL`, `Utility_Bill_URL`
  + extend `BUCKET_FIELD_MAP` to sync tenant uploads to those
- New `<RTRReview>` widget at stage 4 showing per-tenant RTR completeness
- ~1 day of work

### Wave 3 (Financials + close-out) — designed, not started
- `<FinancialsPanel>` at stages 7/8: Deposit_Received, First_Rent_Cleared,
  TDS_Registered, Disbursement_Approved + dates, TDS_Scheme text, commission rate
- Pet request workflow on tenant card (Pet_Request_Received + date)
- Standing order confirmation
- End-of-tenancy actions: Checkout_Date, deposit return, archive property
- ~2 days

### Misc / nice-to-have
- Stage agent assignment dropdown (Stages table → currently no UI for "Stage agent" multipleCollaborators)
- HMO_Licence checklist item + HMO_Licence_Confirmed are separate things —
  ticking the checklist item doesn't flip the Property field. We exposed the
  field directly via PropertyFlags so this works, but the duplication is ugly.
- Auto re-evaluate on PATCH flags when a gate-relevant field flips (with
  email suppression). Considered but deferred.
- Form 4A as a library doc (user said no for now).
- A "review pre-extracted contracts" admin page that lets users re-run the
  extractor from the UI rather than CLI. Low priority.

---

## 8. Known weirdness / gotchas

- **Airtable field name quirks**: `'Annual Rent '` (trailing space),
  `'EPC Rating '` (trailing space), `'Post Code'` (caps + space) on Landlords
  but `'post_code'` (snake) on Properties. Tenants table link to Properties
  is named `'Property Id'` not `'Property'`. Trapped in code; just know.
- **Single-select option drift**: Airtable rejects writes to unknown options.
  - `Result` on Gate_Log: only `Passed`/`Blocked`
  - `Verification Status` on Landlords: `Pending Review`/`Approved`/`Rejected`
  - `ID_Name_Match`: `Pending`/`Confirmed`/`Mismatch`
  - `RTR_Check_Type` on Tenants: `Manual`/`Paragon`/`Online Home Office`
    (Pydantic disagrees — see Wave 2 note above)
  - `Document_Type` on Compliance: `Gas Cert | EPC | How to Rent | Section 8 Notice | Section 21 Notice | Deposit Certificate | Prescribed Info | Other | EICR | RRA Sheet | Ground 4A Notice`
- **Windows fpdf2 fallback** silently produces ugly PDFs because WeasyPrint
  needs GTK. We added Playwright as primary renderer to dodge this — make sure
  Chromium binary is downloaded (`playwright install chromium`).
- **TipTap autolink** wraps `/pg_sigN/` in `<a>` tags. We disabled autolink in
  ContractEditor; backend also defensively unwraps via regex before substitute.
- **`sync_playwright()` under uvicorn on Windows** fails with
  `NotImplementedError` because uvicorn sets SelectorEventLoop. Our renderer
  runs Chromium in a subprocess to get a clean ProactorEventLoop.
- **DocuSign Connect** custom-fields-in-payload requires "Include Custom Fields"
  ticked in the configuration. We have a defensive API fallback in
  `/webhook/docusign` that fetches them via REST when missing, so it works
  either way — but if you ever see "property_not_found" on a webhook, that's
  the cause.

---

## 9. Commands cheatsheet

### Backend dev
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Frontend dev
```bash
cd frontend
npm run dev
```

### Re-extract library docs (after source .docx changes)
```bash
cd backend
python -m scripts.extract_library_docs
```

### Frontend build check
```bash
cd frontend
npx --no-install vite build
```

### ngrok (free tier) for DocuSign webhooks
```bash
ngrok http 8000
```
Then update DocuSign Admin → Connect → your config's URL to the new ngrok URL.
Or use the in-app fallback: `POST /webhook/docusign/poll/{envelope_id}`.

---

## 10. How to resume

Read this file. Then:

1. **`cd C:\Users\asadn\Documents\ZENOLVE\lettingauto`** and `git status` to
   see what's uncommitted on `dev` since the last commit.
2. Skim section 7 (outstanding work) — decide what's next with the user.
3. If continuing Wave 2 / 3, the patterns are established:
   - Backend allowlists in router files (PATCHABLE_FLAGS shape)
   - Frontend uses `<PropertyFlags>` generalised with custom paths
   - Confirmation modals via `useConfirm()` — drop `confirm` block on catalog
   - All changes go through Airtable directly; no caching layer to invalidate

The user has been collaborating on this for ~12 days. They have good context
on the system; lean on them when uncertain rather than guessing.

---

_File generated 2026-05-24 by Claude at the user's request to enable a
session handoff. No code changes were made in this turn._
