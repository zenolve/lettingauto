# Palace Gate Lettings — Implementation Status & Plan

_Last updated: 2026-05-15. Living document — update as work lands._

> ⚠ **TEMPLATES DEFERRED** — extraction of TPL-01..TPL-42 (the 44 correspondence
> templates from the master doc, plus the .docx contract sources in
> `~/Downloads/`) is parked. See **§3** for the inventory and plan. Ping the AI
> when you want to pick this up.

This document is the single source of truth for "what's built vs. what's left"
against the **Palace Gate Master Build Reference v1.0 (April 2026)** and the
107-step **Tenancy Setup Checklist v3.0**. Use it to scope each next turn.

---

## 1. This turn's deliverables (2026-05-15)

| Item | Status | Notes |
|---|---|---|
| DocuSeal mock mode | ✅ Done | Activates whenever `DOCUSEAL_TOKEN` is empty or starts with `REPLACE_ME`. Synthesises a real-looking submission response and stamps it into `MOCK_DOCUSEAL_SUBMISSIONS`. `mock_signed_event(submission_id, template_name)` helper builds a `submission.completed` payload that can be POSTed to `/webhook/docuseal-signed` to drive PG_04 end-to-end without a real DocuSeal instance. |
| File-upload backend | ✅ Done | `POST /api/uploads/{property_id}/{bucket}?token=<form_token>` (public, landlord forms) and `POST /api/uploads/agent/{property_id}/{bucket}` (agent JWT). Files stored under `backend/uploads/<property_id>/<bucket>/<timestamp>_<nonce>_<original>`. Served back via the static `/uploads` mount. Size cap 25 MB; allowed extensions whitelisted; bucket whitelist enforced. |
| Pydantic models clarified | ✅ Done | `LandlordAdminInput` / `LandlordVerificationInput` docstrings note that `*_upload` fields are absolute URLs returned by the upload endpoint. |
| Test coverage of upload flow | ✅ Verified | Live curl test: 201 on valid PDF, 400 on `.exe`, 403 when form-token property_id mismatches. File round-trips through disk and the static mount. |

---

## 2. 107-step checklist — implementation gap analysis

Status legend:
- **✅ Implemented** — handler/UI captures and acts on the field
- **🟡 Partial** — field captured but no validation/diary/action
- **❌ Missing** — not in code at all
- **🔧 Buggy** — implemented but with schema-drift or bug we've already identified

### A — Property take-on & landlord due diligence (steps 1–15)
| # | Step | Status | Notes |
|---|---|---|---|
| 1 | Property details complete | ✅ | `PropertyTakeon.tsx` + `pg01_takeon.py`. Missing: tenure-conditional fields, service charge, ground rent, managing agent on flat. |
| 2 | Tenancy type calc (£100k threshold) | ✅ | `derive_tenancy_type()` |
| 3 | Building manager/concierge details | ❌ | Captured in PG_02 (`block_manager_*`) but only for landlord-admin step, not on take-on |
| 4 | Instruction / Valuation Letter (TPL-01) | ❌ | No template generation yet |
| 5 | T&C of Business (TPL-03) | 🟡 | DocuSeal flow exists; template not pre-filled with merge fields |
| 6 | Service selection (Let Only / RC / FM) | ✅ | `derive_service_level()` |
| 7 | Landlord passport (Land Reg match) | 🟡 | Upload field exists; **no Land Reg match check** |
| 8 | Proof of address (≤3 months) | 🟡 | Upload field exists; **no date-age check** |
| 9 | Company/trust AML (cert of incorp, articles, directors) | 🟡 | Verification form has fields; **no AML rules per non-natural person** |
| 10 | Ownership confirm + lender consent | 🟡 | Upload exists; **no Land Reg check, no mandatory-when-mortgaged enforcement** |
| 11 | Residency (UK / Non-UK) | ✅ | `is_overseas()` |
| 12 | NRL 20% withholding + quarterly accounting | 🟡 | `NRL_Withholding_Active` flag set; **no actual 20% deduction in disbursement, no quarterly HMRC diary** |
| 13 | Head lease (if leasehold) | 🟡 | Upload exists; **no key-restriction extraction into Special Conditions** |
| 14 | Buildings & contents insurance | 🟡 | Upload exists; **no third-party-liability validation** |
| 15 | Land Reg fraud-alert advisory | ❌ | Not in code |z

### B — Property compliance & safety certificates (steps 16–28)
| # | Step | Status | Notes |
|---|---|---|---|
| 16 | Gas Safety Certificate + annual diary | 🟡 | Upload + expiry; **diary writes are 🔧 buggy (`Diary_Type` vs `Type` schema drift); no 10-month auto-reminder** |
| 17 | Boiler service confirmation | ❌ | Not in model |
| 18 | Fireplace inspection (conditional) | ❌ | Not in model |
| 19 | A/C condensers (FM only) | ❌ | Not in model |
| 20 | EICR (5-year, expiry capture) | 🟡 | Same as gas — captured, diary buggy |
| 21 | Smoke + CO alarms | 🟡 | Single checkbox `smoke_detectors_fitted`; no **annual battery check diary** for FM |
| 22 | Legionella risk assessment | ❌ | Not in model |
| 23 | EPC (block if F/G) | 🟡 | Rating captured; **F/G blocking enforced in gate condition `_epc_not_fg` ✅ but no upload, no register link** |
| 24 | Window blind cord safety | ❌ | Not in model |
| 25 | Furniture fire safety (if furnished) | ❌ | Not in model |
| 26 | HMO licence (≥3 unrelated tenants) | 🟡 | `HMO_Flag` set when `number_of_occupants >= 3` in PG_03; **no multi-tenant data model** |
| 27 | Westminster selective licensing | ❌ | `Westminster_Flag` exists in Airtable but no postcode list / no check |
| 28 | Appliance manuals (FM) | ❌ | Not in model |

### C — Marketing & property prep (steps 29–34)
| # | Step | Status | Notes |
|---|---|---|---|
| 29 | Photos + floor plan upload | ❌ | Bucket allowed (`photos`, `floor_plan`); **no form field, no "ready to market" gate** |
| 30 | Pricing letter (TPL-01) | ❌ | No template generation |
| 31 | Portal launch checklist (Rightmove/Zoopla/LonRes/PG site) | ❌ | Not in model |
| 32 | Marketing board (deprecated per master doc) | n/a | Excluded from default workflow per spec |
| 33 | Key cutting / hold-keys authority | ❌ | Not in model |
| 34 | Pre-tenancy works sign-off (TPL-08) | ❌ | Not in model |

### D — Applicant & offer (steps 35–45)
| # | Step | Status | Notes |
|---|---|---|---|
| 35 | Tenant details | ✅ | `OfferInput` |
| 36 | Tenant passport + visa upload | 🟡 | Buckets allowed; **no field on `OfferInput` yet** |
| 37 | Right to Rent check + retention | ❌ | Not captured |
| 38 | Tenant utility bill (≤3 months) | ❌ | Not captured |
| 39 | Offer letter to LL (TPL-05) | 🟡 | DocuSeal offer letter call exists (now mocked); template merge fields incomplete |
| 40 | APT vs Common Law term enforcement | ✅ | `validate_apt()` blocks if APT has end_date |
| 41 | Anti-discrimination checkbox | ✅ | Gate condition `Anti_Discrimination_Confirmed` for APT |
| 42 | Rent in advance ≤1 month (APT) | ✅ | `validate_apt()` checks `rent_in_advance_months` |
| 43 | Written LL acceptance | 🟡 | Comes via DocuSeal callback in PG_04 |
| 44 | Holding deposit (max 1 wk APT) | 🟡 | Field captured; **15-day deadline alert not in code** |
| 45 | Holding deposit receipt | ❌ | Not generated |

### E — Referencing & guarantor (steps 46–51)
| # | Step | Status | Notes |
|---|---|---|---|
| 46 | Paragon reference number | ❌ | No field on Tenant |
| 47 | Outcome (Pass / Conditional / Fail) | 🟡 | `Referencing_Status` field exists; no Paragon integration |
| 48 | Guarantor required determination | ❌ | No logic; guarantor fields just optional in offer |
| 49 | Guarantor referencing + deed | 🟡 | Guarantor name/email captured; no deed upload field |
| 50 | Notify LL of referencing result | ❌ | Not implemented |
| 51 | Identity discrepancy block | ❌ | Not enforced |

### F — Tenancy Agreement & pre-completion (steps 52–62)
| # | Step | Status | Notes |
|---|---|---|---|
| 52 | Pick TA template by tenancy type | 🟡 | ContractEditor exists; template selection logic not by tenancy_type |
| 53 | Prescribed info + **Section 13/Form 4A 9.5-month diary** | 🔧 | CRITICAL — diary handler buggy |
| 54 | Send draft to LL + TT | 🟡 | DocuSeal flow exists |
| 55 | Special conditions / break / pet | 🟡 | `OfferInput.special_conditions` free-text only; no structured pet/break-clause field |
| 56 | Remove rent review clauses (APT) | ❌ | Template-level — needs handling in contract editor |
| 57 | Prep fee (Common Law only) | ❌ | Not in financial model |
| 58 | Bank details with SWIFT/IBAN | 🟡 | TPL-09 not generated; bank details captured per landlord |
| 59 | Finalise TA with version tracking | ❌ | No version history |
| 60 | LL signature (name match check) | 🟡 | DocuSeal callback wires `TA_LL_Signed`; no name-match validation |
| 61 | TT + occupier signatures | 🟡 | Same |
| 62 | Ground 4A notice (student APT, by 31 May 2026) | ❌ | Not in code |

### G — Financials & funds (steps 63–70)
| # | Step | Status | Notes |
|---|---|---|---|
| 63 | First rent demand (TPL-09) | ❌ | Not generated |
| 64 | Cleared funds gate | ✅ | `funds_cleared` flag in gate transitions |
| 65 | Reservation fee offset | ❌ | Not in model |
| 66 | Standing order mandate | ❌ | Not in TPL |
| 67 | Commission + disbursement | 🟡 | `Commission_Rate` field; no calc/disbursement workflow |
| 68 | NRL 20% + annual 5-April cert | ❌ | No diary, no cert generation |
| 69 | SDLT advisory | ❌ | Not in tenant pack |
| 70 | T&C-on-file gate before disbursement | ❌ | Not enforced |

### H — Deposit protection (steps 71–74)
| # | Step | Status | Notes |
|---|---|---|---|
| 71 | TDS registration within 30 days (APT) | 🟡 | `TDS Cert On File` field; no 30-day countdown |
| 72 | Prescribed Information service | ❌ | No PDF generation |
| 73 | TDS membership annual fee | ❌ | Not in code |
| 74 | TDS cert upload | 🟡 | `tds_certificate` bucket allowed; no UI yet |

### I — Pre check-in & move-in (steps 75–79)
| # | Step | Status | Notes |
|---|---|---|---|
| 75 | Professional clean | ❌ | Not in model |
| 76 | Inventory clerk | 🟡 | `Inventory_Clerk` field; no booking workflow |
| 77 | Check-in appointment (TPL-10) | ❌ | Not generated |
| 78 | Key sets (min 2 to tenant) | ❌ | Not captured |
| 79 | Cut additional keys | ❌ | Not in model |

### J — Tenant pack & prescribed documents (steps 80–90)
| # | Step | Status | Notes |
|---|---|---|---|
| 80 | How to Rent handbook (APT) | 🟡 | `How_To_Rent_Served` flag; no PDF attached, just a checkbox |
| 81 | Gas cert served | 🟡 | `Gas_Cert_Served` flag; no PDF attached |
| 82 | EPC served | 🟡 | `EPC_Served` flag; no PDF attached |
| 83 | EICR served | 🟡 | `EICR_Served` flag; no PDF attached |
| 84 | TDS Prescribed Info served | 🟡 | `TDS_Info_Served` flag; no PDF generated |
| 85 | **RRA Information Sheet (DEADLINE 31 May 2026)** | 🔧 | `RRA_Sheet_Served` flag; **no batch send-to-all-active-APT, no PDF attach** |
| 86 | Welcome letter (TPL-11) | ❌ | Not generated |
| 87 | Appliance manuals (FM) | ❌ | Not in model |
| 88 | Pet rights notice + 28-day timer | ❌ | Not in model |
| 89 | Head lease excerpts to tenant | ❌ | Not in code |
| 90 | Insurance excerpts to tenant (FM) | ❌ | Not in code |

### K — Post move-in & utilities (steps 91–95)
| # | Step | Status | Notes |
|---|---|---|---|
| 91 | Utility transfer template (TPL-13) | ❌ | Not generated |
| 92 | Council tax notification | ❌ | Not in TPL |
| 93 | Telephone/broadband/satellite (advisory) | ❌ | Not in TPL |
| 94 | Distribute signed TA | 🟡 | DocuSeal returns it; no auto-distribute |
| 95 | Distribute inventory + check-in report | ❌ | Not implemented |

### L — Diary & ongoing compliance (steps 96–107)
| # | Step | Status | Notes |
|---|---|---|---|
| 96 | Rent review diary (9.5-month APT / 3-month CL) | 🔧 | Code writes to Diary with wrong field names |
| 97 | Gas annual diary | 🔧 | Same |
| 98 | EICR 5-year diary | 🔧 | Same |
| 99 | Break clause diary | ❌ | Not in code |
| 100 | Tenancy expiry diary + Memo of Extension (CL) | ❌ | Not in code |
| 101 | How to Rent re-serve on new edition | ❌ | Not in code |
| 102 | RTR follow-up on time-limited visas | ❌ | Not in code |
| 103 | NRL annual cert 5 April | ❌ | Not in code |
| 104 | RRA batch to all active APT (31 May 2026) | ❌ | **DEADLINE — must be implemented before 31 May 2026** |
| 105 | S21 block from 1 May 2026 | ❌ | Not in code |
| 106 | PRS Ombudsman (~2028) | ❌ | Future |
| 107 | PRS Database (~2028) | ❌ | Future |

**Summary**: 7 fully implemented (✅), 36 partial (🟡), 5 buggy with known fix (🔧), 59 missing (❌).
Most critical gaps: prescribed-document attachment (steps 80–85), diary entries (96–104), RRA batch (104 — May 2026 deadline), and rent-review Section 13 alert (53/96).

---

## 3. Correspondence template library (TPL-01..42) — inventory

All 44 templates from the master doc (TPL-01..42 plus TPL-35a/b/c). **None are
currently extracted as code-rendered templates.** The contract editor in
`backend/app/templates/contracts/` covers only T&C, Offer Letter, and Tenancy
Agreement HTML shells — no merge-field placeholders, no Palace Gate branding,
no per-stage trigger.

### Templates by stage
- **Stage 1 — Take-on / Landlord instructions**: TPL-01 (Intro Valuation), TPL-02 (Instruction Letter), TPL-03 (KYC Request), TPL-04 (T&C Reminder)
- **Stage 2 — Compliance**: TPL-07 (Legal Reqs Checklist), TPL-08 (Pre-Tenancy Works Sign-Off)
- **Stage 3 — Offer**: TPL-05 (Offer Confirmation to LL), TPL-06 (Referencing Request to TT)
- **Stage 4 — Pre move-in**: TPL-09 (Bank/SO Mandate), TPL-10 (Check-In Confirmation), TPL-11 (Welcome + Full Tenant Pack), TPL-12 (Move-In Confirmation to LL), TPL-13 (Utility Transfer)
- **Stage 5 — Rent collection (cycle)**: TPL-14..17 (rent reminders / arrears)
- **Stage 6 — Maintenance**: TPL-18..23 (acknowledge / instruct / chase / complete)
- **Stage 7 — Periodic LL/TT touches**: TPL-24..31
- **Stage 8 — Renewal**: TPL-32..34
- **Stage 9 — End of tenancy**: TPL-35a/b/c (notice types), TPL-36..42

### Plan
1. Read each `.docx` source (Intro Valuation Letter, Instruction Letter, T&C, APT Pet ABNB, Common Law TA, RRA info sheet, Tenancy Checklist, Form 4A).
2. For each template that the master doc names as content-bearing (not info-only), extract the body and mark every blank, `[bracketed]`, and `_____` with a Jinja2 placeholder bound to a merge-field name.
3. Save as `backend/app/templates/correspondence/TPL-XX_*.html` (HTML for email/PDF rendering) and `.txt` (plain-text fallback).
4. Store the original `.docx` sources unchanged under `backend/app/templates/correspondence/source/` for reference.
5. Add a `templates.py` index module that maps `TPL-XX` → template path + required merge fields.
6. **Info-only documents** (per master doc): "Renters' Rights Act Information Sheet" PDF and "Form 4A" PDF should be stored as-is and served via the static `/templates` mount, not regenerated.

---

## 4. Frontend re-scope (not done — needs a focused turn)

Issues user flagged:
1. **Take-on page shows documents/contracts that shouldn't be there yet** — those belong on compliance (stage 2 in our model) after the landlord admin form is submitted.
2. **Agent doesn't need to fill the PG_02 form** — it's the landlord's form (sent via the verification email link). The agent's job is to edit DocuSeal documents via the contract editor.
3. **Stage chips in `StagePipeline` are not clickable** — visual only. User expected per-stage navigation.

### Plan
- Convert `StagePipeline` chips into navigation buttons (`<Link to={...}>`).
- Add a per-stage view layout: `/agent/properties/:id/stage/:order` with cards/widgets that filter to that stage's relevant entities.
- On `PropertyDetail` (the default landing), render only the cards that map to the current stage. Specifically:
  - **Stage 1 (Take-on)**: Property + Landlord cards. No Contracts card yet.
  - **Stage 2 (Compliance)**: Property compliance status (gas/EPC/EICR), uploaded documents preview, T&C signing status.
  - **Stage 3 (Marketing)**: Photos, floor plan, portals checklist.
  - **Stage 4 (Offer)**: Tenant card, offer letter editor, APT/CL warnings.
  - **Stage 5 (Referencing)**: Paragon ref, results, guarantor sub-flow.
  - **Stage 6 (TA Signing)**: TA editor + DocuSign-style status grid.
  - **Stage 7 (Pre Move-in)**: Inventory, keys, clean date, prescribed-doc service tracker.
  - **Stage 8 (Live tenancy)**: Diary entries, rent collection status, maintenance log.
  - **Stage 9 (End of tenancy)**: Notice served, check-out, deposit release.
- Remove the agent's standalone `LandlordAdmin` page entry (it should only ever be reached via the public form-token URL); replace agent's view of stage 2 with a "documents to edit" card surfacing TPL-07 + T&C + Instruction Letter editors.

---

## 5. Property flow viewer (Miro-style) — not started

User spec: "implement a separate flow feature where the admin can come in and
view the current flow of steps and the documents involved. This should be made
dynamically after fetching a property's data. This feature should look like a
miro board."

### Plan
- Route: `/agent/properties/:id/flow`
- Backend endpoint: `GET /api/properties/{id}/flow` that aggregates:
  - Current stage + gate status
  - All submissions (Airtable Submissions table)
  - All DocuSeal submissions (real + mock)
  - All diary entries
  - All uploaded documents per bucket
  - All compliance/financial/checklist linked records
- Frontend: A canvas-style page using **React Flow** (recommended over a from-scratch Miro clone — same draggable-node UX with minimal code). Nodes:
  - Stage nodes (one per the 9 stages)
  - Document nodes (one per uploaded file or generated template)
  - Person nodes (landlord, tenant, agent)
  - Diary nodes (pending alerts)
- Edges: derived from data relationships (property → landlord, stage → documents triggered on it, etc.).
- Default zoom: fit to viewport. Pan/zoom enabled. Click a node → side panel with details + jump-to-record link.
- Out of scope for v1: editing, real-time collab.

---

## 6. Other open items (carried from previous turns)

- **Airtable schema drift** in Diary, Gate_Log, and Compliance writes. Earlier turns flagged exact field-name mismatches; either fix code or rename Airtable fields. See conversation log dated 2026-05-14.
- **`ADMIN_EMAIL` typo in `.env`**: `asad@plondonproperty.co.uk` — extra "p". Stage 5 has no "Stage agent" populated so notifications fall back to `ADMIN_EMAIL`.
- **Multi-landlord / multi-tenant data model**: Master doc step 26 requires "system must support multiple landlords and multiple tenants per property". Currently 1:N from landlord side via Properties linked list, but offer flow assumes a single tenant. Needs design.

---

## 7. Recently shipped

| Date | Item | Notes |
|---|---|---|
| 2026-05-15 | Frontend re-scope | Stage chips clickable; per-stage cards via `?stage=N`; contracts no longer on take-on; current-stage derived from data |
| 2026-05-15 | Gate_Log schema-drift fix | Writes now use `Attempted_At` / `From_Stage` / `To_Stage` / `Result` / `Block_Reason`. Verified live row from PG_02 gate eval. |
| 2026-05-15 | Diary schema-drift fix | All four call sites (pg02_admin NRL, pg02b_verification NRL, pg04_docuseal TA-signed entries) now use `Diary_Type` / `Diary Date` / `Alert_Message`. Removed non-existent `Landlord` link. |
| 2026-05-15 | **Section 13 / Form 4A alert (step 53/96)** | `_create_ta_diary_entries` writes a `Rent Review S13` diary entry at `start + 9.5 months` when PG_04 records TA-fully-signed. Critical pre-existing deadline. |
| 2026-05-15 | Miro-style flow viewer | `/api/properties/{id}/flow` + `/agent/properties/:id/flow` using `@xyflow/react`. Aggregates stages, property, landlord, tenant, uploads, submissions, diary, gate log. Verified live: 24 nodes for our test property. |
| 2026-05-15 | Marketing assets UI (step 29) | Reusable `FileUploader` component; wired `photos` and `floor_plan` upload widgets on Stage 3 with "Ready to market" status pill. |
| 2026-05-15 | **Tenant-pack PDF service (steps 80–85)** | `services/prescribed_docs.py` generates branded PDF placeholders for How-to-Rent / Gas / EPC / EICR / Prescribed Info / RRA / Ground 4A. WeasyPrint with pure-Python fpdf2 fallback (no GTK needed on Windows). PG_05 attaches all PDFs to a single tenant email, persists each to `uploads/<property>/served_<doc>/`, writes a Compliance audit row per doc with `Served_As=PDF Attachment`. Verified live: all 6 audit rows landed for our APT test property. |
| 2026-05-15 | RRA batch (step 104) | PG_07 now uses the same prescribed-docs service to serve the RRA Sheet as a PDF attachment to **every named tenant** on every APT property not yet served. Per-tenant loop. Critical 31 May 2026 deadline. |
| 2026-05-15 | Right to Rent capture (steps 35–38) | `OfferInput` carries `tenant_passport_upload` / `tenant_visa_upload` / `tenant_utility_bill_upload` / `rtr_check_type` / `rtr_check_date` / `rtr_doc_reference` / `visa_expiry_date`. PG_03 stores RTR fields on Tenant, writes per-doc Compliance audit rows, and schedules an `RTR Followup` diary entry 60 days before visa expiry. |
| 2026-05-15 | Paragon mock (step 46) | `core/paragon_client.py` with the same mock pattern as DocuSeal — auto-activates when `PARAGON_TOKEN` is empty or `REPLACE_ME`. PG_03 instructs Paragon on offer and writes the returned reference to `Tenants.Referencing_Paragon_Ref`. |
| 2026-05-15 | Multi-landlord / multi-tenant (step 26) | `OfferInput.co_tenants: list[CoTenantInput]` creates one Tenant record per additional named occupant; PG_03 links them all to `Properties.Tenant`; HMO flag re-derived from total count. PG_05 and PG_07 iterate every named tenant and serve the pack/RRA to each. |
| 2026-05-15 | Compliance table id fix | `.env` had `AIRTABLE_TABLE_COMPLIANCE=fldsoZsRfzDIJ8MY5` (a field id, not a table id). Updated to `tblr59bPp9oUusMgJ`. All Compliance writes now succeed. |

## 8. Proposed next turns (priority order)

1. **Templates extraction (TPL-01..42)** — biggest single chunk of remaining master-doc work. Deferred per user instruction; banner at the top of this doc.
2. **WeasyPrint native deps on the dev machine** — installing GTK / Pango / Cairo on Windows so the prescribed-doc PDFs use the proper branded HTML rendering instead of the plainer fpdf2 fallback. The fallback works but is cosmetically inferior.
3. **Pre-tenancy works sign-off (step 34)** + tenant pack gate updates: today the prescribed-docs pack flips `*_Served=True` but does not validate that the underlying source PDFs are real (we serve placeholders). Once template extraction lands, swap the placeholder bodies in `DOC_DEFS` for the real source PDFs.
4. **Paragon webhook receiver** — PG_03 instructs Paragon (mocked); we need an inbound endpoint to ingest the outcome (Pass/Conditional/Fail), update `Tenants.Referencing_Status`, and fire the Stage 5→6 gate.
5. **Multi-tenant DocuSeal flow** — currently PG_04 only matches the first tenant by email when wiring TA signatures. Should match all.

---

## 8. How to validate this turn's changes locally

```powershell
# 1. DocuSeal mock — kick off PG_03 and observe the mock-id in the response
$login = Invoke-RestMethod http://127.0.0.1:8001/auth/login -Method Post -ContentType application/json -Body (@{email='admin@palacegate.com';password='ChangeMeImmediately!'} | ConvertTo-Json)
# ... POST /api/forms/offer/<property_id> — response will include a mock docuseal_url

# 2. File upload — mint a form token, then upload a PDF
curl.exe -X POST -F "file=@my.pdf" "http://127.0.0.1:8001/api/uploads/<property_id>/mortgage_consent?token=<form_token>"
# → 201 with {"url":"http://localhost:8000/uploads/<property_id>/mortgage_consent/...pdf"}

# 3. Replay a mock DocuSeal "signed" webhook (Python shell on the backend host)
python -c "from app.core.docuseal_client import mock_signed_event, MOCK_DOCUSEAL_SUBMISSIONS; sid = next(iter(MOCK_DOCUSEAL_SUBMISSIONS)); import json; print(json.dumps(mock_signed_event(sid, 'Offer Letter')))"
# → POST that JSON to /webhook/docuseal-signed to drive PG_04
```
