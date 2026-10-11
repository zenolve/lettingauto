# Backlog

Deferred work, written so it can be picked up cold. Each item says what is
true today, what to build, and any decision still owed by the business.

---

## Sent-document versioning — phase 2: keep the signed copy

**Today** (phase 1, migration 004): every send has a version, links to the
send it replaced, and keeps the HTML that went out (`sent_document_bodies`).
When the signing provider reports completion, `pg04` →
`update_status_by_envelope` flips the row to *Signed* — but `PDF URL` still
points at the **unsigned** render. The executed document exists only inside
DocuSign / DocuSeal.

**Build**
- On the completion webhook, download the signed PDF (DocuSign:
  `GET /envelopes/{id}/documents/combined`; DocuSeal: the submission's
  documents) and store it beside the unsigned one under the property's
  uploads volume.
- New migration: `sent_documents.signed_pdf_url`; registry entry; show
  *View signed PDF* on the property page.
- Cover the offer letter (`pg03`, DocuSeal) as well as library sends.
- Small add-on: a read-only *View copy* for sends with no PDF (email-only),
  served from `sent_document_bodies` — today only *Revise* surfaces it.

**Size:** ~½ day.

---

## Sent-document versioning — phase 3: template history

**Today:** `PUT /api/library/{doc}/raw` overwrites
`templates/library/{doc}.html` in place — no history. On the droplet the
templates directory is part of the Docker image, so an edit made in the UI is
lost at the next deploy.

**Build**
- Move template bodies into Postgres (`library_templates` +
  `library_template_versions`, agency-scoped so each agency can customise),
  with the shipped file as seed/fallback behind `get_body`.
- Editor: version history with restore.
- Record which template version each send used on `sent_documents`.

**Size:** ~1 day.

---

## Re-letting a property after a tenant leaves — not supported

**Findings (Oct 2026)**
- The property row *is* the tenancy. Tenancy flags (`TA_LL_Signed`,
  `TA_TT_Signed`, `LL_Offer_Accepted`, deposit fields, every `*_Served`
  flag, `funds_cleared`, tenancy dates, `Properties.Tenant`) sit beside the
  property-level ones (landlord link, certificates, `TC_Signed`).
- The stage is derived from those flags, most-advanced first
  (`properties._derive_stage_order_from_fields`,
  `forms._derive_current_stage_for_check`, `stages.ts`). Nothing derives
  stage 9, so *End of Tenancy* is never reached.
- The UI hides *Record an offer* once a tenant is linked, but the offer route
  and API only check `stage >= 4`. A new offer accepted on a live property
  swaps `Properties.Tenant` while the previous tenancy's signatures, deposit
  and served flags stay true — the new tenancy would read as Live with no
  referencing, no signed agreement and nothing served to the new tenant.
- What already survives a change of tenant: tenant rows (via
  `Tenants."Property Id"`), offers, sent documents, gate log, diary.
- The only way to start a new tenancy today is a new take-on: the landlord is
  re-entered (a duplicate landlord row), the £50 is charged again, and the
  history is split across two property records.

**Proposed**
1. *End tenancy* — record the end / checkout date and derive stage 9 from it;
   the end-of-tenancy templates (TPL-32…42) belong here.
2. *Re-let* — archive the tenancy into a `tenancies` table (tenants, dates,
   rent, deposit, flag snapshot, links to its documents), clear the
   tenancy-scoped fields, cancel that tenancy's pending diary alerts. Property
   data stays: landlord, certificates and expiries, EPC, HMO licence,
   insurance, consents. The derived stage then falls to 4 (Offer) — or earlier
   if a certificate has expired in the meantime, which is the right outcome.
3. Guard the offer API: refuse a new offer while an accepted tenancy is live.
4. Property page: *Previous tenancies*.
5. Scope sent-document version chains to a tenancy, so a new tenancy's
   agreement is not offered as a revision of the last one (today the agent
   unticks *This replaces vN*).

**Decisions needed**
- Is a re-let a new £50 tenancy, collected pay-first like take-on?
- Does `TC_Signed` (the landlord's terms of business) carry over to a re-let?
- Restart at Offer (stage 4) or Marketing (stage 3)?

**Size:** ~1½–2 days once decided.
