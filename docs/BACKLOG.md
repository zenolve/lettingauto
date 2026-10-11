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
