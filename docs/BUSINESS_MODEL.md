# LettingAuto — Business Model

> Sole purpose of this document: explain how this product creates and captures
> value, to any reader — human or AI agent — with zero prior context. For
> technical architecture see `../CLAUDE.md`; for operator setup see
> `COMMERCIAL_SETUP.md`.

---

## 1. What the product is, in one paragraph

LettingAuto is a multi-tenant SaaS for **UK letting agencies** (the businesses
that let and manage rental properties on behalf of landlords). It runs the
entire life of a tenancy as a nine-stage pipeline — property take-on,
compliance, marketing, offer, referencing, contract signing, pre-move-in,
live tenancy, end of tenancy — with **hard compliance gates** between stages:
a tenancy physically cannot advance until the legally required items (gas
safety certificate, EPC, EICR, How-to-Rent guide, deposit protection,
Right-to-Rent checks) are in place. Around that spine it provides
agency-branded contracts and e-signing, landlord/tenant onboarding forms,
referencing, document audit trails, and payments.

## 2. The problem it solves (why anyone pays)

UK lettings is one of the most regulation-dense consumer industries:

- Missing a prescribed document can **block possession proceedings** (the
  agency's landlord client can't evict a non-paying tenant — career-ending
  for the agency relationship).
- The Renters' Rights Act 2025 added new prescribed information with fines
  up to **£7,000 per breach**.
- Deposit protection has a hard 30-day statutory clock; holding deposits a
  15-day one; certificates expire on their own schedules.

Most small/mid agencies track all of this in spreadsheets, inboxes and
memory. LettingAuto's pitch is that the *system* carries the compliance
burden: gates block unsafe progress, documents are served and logged
automatically, deadlines become diary alerts. The buyer is the agency
principal; the daily user is the lettings agent.

## 3. How it makes money

**One price: £50, one-time, per new tenancy started. Nothing else.**

- No subscription, no per-seat fees, no tiers, no onboarding fee.
- The fee is charged **at the moment the agency starts a new tenancy**
  (creating a property/tenancy in the pipeline), via Stripe Checkout.
- Payment is **collected before anything is created** ("pay-first"): the
  agency submits the new-tenancy form, is sent to Stripe, and the tenancy
  records only materialise when the £50 clears. Abandoned checkouts cost
  nothing and create nothing.

### Why this pricing shape (the rationale)

1. **Aligned with the customer's own revenue event.** An agency only starts a
   new tenancy when it is about to earn a let fee / management commission
   (typically hundreds to thousands of pounds). £50 lands exactly when the
   agency has money coming in — it prices as a rounding error against their
   fee, not as a standing cost to justify.
2. **Zero barrier to adoption.** An agency can register, connect nothing, pay
   nothing, and explore the whole product. The first invoice arrives only
   with their first real tenancy. This suits the long-tail of small agencies
   that resist per-seat SaaS commitments.
3. **Self-serve growth.** Sign-up (Supabase auth), agency registration,
   onboarding tour and payment are fully self-service — no sales motion
   required to start collecting revenue.
4. **Simple to reason about and to bill.** One SKU, one Stripe Checkout per
   event, no metering/proration machinery. (A £5/month per-live-tenancy
   subscription existed briefly and was deliberately removed for simplicity.)

### Unit economics sketch

- Revenue per tenancy: £50, minus Stripe's fee (~1.5% + 20p UK cards ⇒ ~£0.95)
  → **~£49 gross per tenancy event**.
- Marginal cost per tenancy is near zero: Supabase Postgres rows, a few
  emails (SMTP), PDF generation on our compute.
- E-signature costs are **not carried by the platform**: signing runs through
  the agency's own provider (DocuSign envelopes consume the agency's plan;
  the roadmap default is self-hosted DocuSeal at zero marginal cost).
- Fixed costs: Supabase project, a small VM/droplet for the API, domain/TLS,
  Stripe account. All flat and small relative to per-tenancy revenue.

So the model is effectively **pure-margin transactional revenue on top of a
flat, low fixed base** — break-even at a handful of tenancies per month.

## 4. Who the actors are and what each one pays

| Actor | Relationship | Pays? |
|---|---|---|
| **Agency** (customer) | Registers itself, owns its data, brands its documents | £50 per new tenancy, via card at checkout |
| Agent (agency staff) | Daily user under the agency's account | Nothing (no seats) |
| Landlord | The agency's client; fills onboarding/verification forms via emailed links | Nothing to us |
| Tenant | Receives prescribed documents, signs contracts, may pay deposits via Stripe | Nothing to us (their deposit/rent payments are agency↔tenant money, not platform revenue) |
| Platform (us) | Operates the SaaS, the Stripe account, the shared infrastructure | Stripe fees + flat infra |

Multi-tenancy note: every agency's data is hard-isolated (row-level
`agency_id` scoping enforced in the API layer + database RLS), and every
outbound artifact — contracts, emails, prescribed documents — carries the
**agency's own name and colours**, not ours. The platform brand
("LettingAuto") appears only in the app chrome and marketing site.

## 5. The money flow, mechanically

```
Agency clicks "New property" and submits the form
        │   nothing is created yet — payload is held as a pending intent
        ▼
Stripe Checkout (one-time £50, the platform's Stripe account)
        │   abandon → nothing exists, intent expires harmlessly
        ▼ pays (their card)
Stripe webhook / success-page verification confirms payment
        ▼
Tenancy records are created; the £50 payment row is permanently linked to
the agency AND the specific property (full attribution + audit trail)
```

Payments are recorded per agency in the `payments` table
(`payment_type = "tenancy_setup_fee"`); the Settings → Billing screen shows
each agency its fees paid/pending. With Stripe unconfigured (development),
billing silently disables and tenancies are free — the product remains fully
usable for evaluation.

## 6. Pricing surfaces — keep these consistent (note for AI agents)

The £50 figure and the "no subscription" claim are stated in ALL of the
following places. **If pricing ever changes, every one of these must be
updated together:**

| Surface | Location |
|---|---|
| The actual charge | `backend/app/config.py` → `stripe_tenancy_setup_fee_pence` (5000) |
| Billing logic | `backend/app/services/billing.py` (intent creation + `billing_summary`) |
| Settings → Billing card | `frontend/src/pages/Settings.tsx` |
| Onboarding modal, slide 4 | `frontend/src/components/OnboardingModal.tsx` (reads the API value, copy mentions it) |
| New-property form copy | `frontend/src/pages/forms/PropertyTakeon.tsx` |
| Login footer microcopy | `frontend/src/pages/Login.tsx` |
| Landing pages (all 3 drafts) | `frontend/design-previews/{D_aurora_glass,E_bento_dark,F_editorial_mesh}.html` + `index.html` |
| Operator docs | `docs/COMMERCIAL_SETUP.md`, `README.md` |

The frontend reads the live price from `GET /api/agencies/me` →
`billing.pricing.tenancy_setup_fee` where possible; static marketing copy
does not.

## 7. Known levers and roadmap (not yet built)

- **DocuSign connector (premium candidate).** Agencies connect their own
  DocuSign via OAuth; envelopes bill to their plan. Could be offered as a
  paid add-on while self-hosted DocuSeal stays the free default. (Plan
  exists; not implemented.)
- **Tenant-payment rails.** Holding deposits/rent already flow through Stripe
  Checkout scaffolding — a per-transaction platform fee (Stripe Connect)
  is a natural future revenue line, but is NOT part of the current model.
- **Volume pricing.** Nothing stops per-tenancy discounting for high-volume
  agencies later; the single-SKU model makes that an easy addition.

## 8. What this model is NOT

- Not per-seat (agents are free and unlimited per agency).
- Not a subscription (nothing recurs; £5/month per live tenancy was removed).
- Not a marketplace and not taking a cut of rent or deposits today.
- Not white-label resale — agencies brand their *documents*, but the app is
  one shared platform.
