import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";

import { Field, Section } from "../../components/ui/Field";
import { PublicUpload } from "../../components/ui/PublicUpload";
import { publicApi } from "../../lib/api";

type YN = "Yes" | "No";

/**
 * PG_02 Landlord Admin form. Field set + conditional logic mirrors the
 * original Tally form (xXj10k) on a single page. Sections kept in Tally
 * order so a landlord who has used the Tally version recognises it.
 *
 * Conditionals (in addition to backend Pydantic validators):
 *   • Mortgage consent upload — visible only when `consent_mortgagor = Yes`
 *   • Tax flow:
 *       has_tax_exempt_number = Yes → NRL approval number input
 *       has_tax_exempt_number = No  → "Will you be applying to IR?"
 *           applying_for_nrl = No   → "Will PG manage NRL?"
 *       appoint_solicitor_for_tax = Yes → tax agent name + address + contact
 *   • Photos uploads / "PG to arrange" — gated on has_photos
 *   • Inventory "PG to arrange" — gated on has_inventory = No
 *   • Leasehold extras (unexpired term, service charge, ground rent, head
 *     lease upload, freeholder consent + upload) — gated on tenure = Leasehold
 *   • Third-party manager — gated on who_manages_property containing "Other"
 *   • Insurance provider / policy / cert — gated on insurance_in_place = Yes
 *   • Gas / EPC / EICR — has_x = Yes → expiry + upload; has_x = No → arrange
 *   • Alternative access textarea — gated on supply_keys = No
 */
type AdminForm = {
  property_post_code: string;
  // block manager
  block_manager_name?: string;
  block_manager_address?: string;
  block_manager_postal_code?: string;
  block_manager_contact?: string;
  block_manager_email?: string;
  // consents
  consent_sublet?: YN;
  consent_mortgagor?: YN;
  mortgage_consent_upload?: string;
  // landlord identity
  landlord_full_name: string;
  landlord_full_address: string;
  landlord_post_code: string;
  landlord_mobile: string;
  landlord_email: string;
  // residency / NRL
  residency: string;
  has_tax_exempt_number?: YN;
  nrl_approval_number?: string;
  applying_for_nrl?: YN;
  pg_manage_nrl?: YN;
  pg_collect_pay_tax?: YN;
  appoint_solicitor_for_tax?: YN;
  tax_agent_name?: string;
  tax_agent_address?: string;
  tax_agent_contact?: string;
  written_to_inland_revenue?: YN;
  // bank
  bank_name?: string;
  bank_address?: string;
  sort_code?: string;
  account_name?: string;
  account_number?: string;
  // listing
  has_photos?: YN;
  auth_photos?: YN;
  has_inventory?: YN;
  auth_inventory?: YN;
  // property characteristics
  property_type?: string;
  tenure?: string;
  unexpired_term?: string;
  annual_service_charge?: number;
  ground_rent?: number;
  head_lease_upload?: string;
  freeholder_consent?: YN;
  freeholder_consent_upload?: string;
  who_manages_property?: string;
  third_party_manager?: string;
  insurance_in_place?: YN;
  insurance_provider?: string;
  insurance_policy_number?: string;
  insurance_cert_upload?: string;
  // utilities (textareas — match Tally placeholders)
  telephone_provider_account?: string;
  gas_provider_meter?: string;
  electricity_provider_meter?: string;
  water_provider?: string;
  cable_tv_details?: string;
  council_tax_borough?: string;
  // utility locations
  gas_tap_location?: string;
  water_stopcock_location?: string;
  electricity_main_switch?: string;
  refuse_collection_day?: string;
  // certificates — required per Tally
  has_gas_cert: YN;
  arrange_gas_cert?: YN;
  gas_cert_expiry?: string;
  gas_cert_upload?: string;
  has_epc: YN;
  arrange_epc?: YN;
  epc_rating?: string;
  epc_upload?: string;
  has_eicr: YN;
  arrange_eicr?: YN;
  eicr_expiry?: string;
  eicr_upload?: string;
  smoke_detectors_fitted: YN;
  furniture_fire_regs?: YN;
  // access
  supply_keys?: YN;
  alternative_access?: string;
};

// Service-level options match Tally's "Who will manage the property?" answers.
const SERVICE_OPTIONS = [
  "Palace Gate Will Manage",
  "I will Manage but PG collects rent",
  "I will Manage",
  "Other manages but PG collects rent",
  "Other",
];

export default function LandlordAdmin() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const { register, handleSubmit, watch, setValue, formState: { errors, isSubmitting } } = useForm<AdminForm>();
  const [done, setDone] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [tokenInfo, setTokenInfo] = useState<any>(null);
  const [tokenError, setTokenError] = useState<string | null>(null);

  // Prefill landlord_email from the JWT once it loads — the link was sent to
  // that address, so it is authoritative. Keeps a user from mistakenly typing
  // their own email into the Block Manager Email field above.
  useEffect(() => {
    if (tokenInfo?.email) {
      setValue("landlord_email", tokenInfo.email);
    }
  }, [tokenInfo, setValue]);

  // ---- File uploads ------------------------------------------------------
  const [uploads, setUploads] = useState<Partial<Record<
    "mortgage_consent_upload" | "head_lease_upload" | "freeholder_consent_upload"
    | "gas_cert_upload" | "epc_upload" | "eicr_upload" | "insurance_cert_upload",
    string
  >>>({});

  function setUpload<K extends keyof typeof uploads>(key: K, url: string | undefined) {
    setUploads((cur) => ({ ...cur, [key]: url }));
    setValue(key as any, url ?? "");
  }

  useEffect(() => {
    if (!token) { setTokenError("Missing token in URL."); return; }
    publicApi.get(`/auth/form-token?token=${encodeURIComponent(token)}&form=landlord_admin`)
      .then((r) => setTokenInfo(r.data))
      .catch((e) => setTokenError(e?.response?.data?.detail ?? "Invalid or expired link"));
  }, [token]);

  // ---- Watches for conditional rendering --------------------------------
  const tenure = watch("tenure");
  const consentMortgagor = watch("consent_mortgagor");
  const hasTaxExempt = watch("has_tax_exempt_number");
  const applyingForNrl = watch("applying_for_nrl");
  const appointSolicitor = watch("appoint_solicitor_for_tax");
  const hasPhotos = watch("has_photos");
  const hasInventory = watch("has_inventory");
  const whoManages = watch("who_manages_property");
  const insuranceInPlace = watch("insurance_in_place");
  const hasGas = watch("has_gas_cert");
  const hasEpc = watch("has_epc");
  const hasEicr = watch("has_eicr");
  const supplyKeys = watch("supply_keys");

  const showThirdPartyManager = whoManages === "Other" || whoManages === "Other manages but PG collects rent";

  // ---- Submit -----------------------------------------------------------
  async function onSubmit(values: AdminForm) {
    setServerError(null);
    // Strip empties + merge uploads so optional EmailStr/date/float fields
    // don't 422 on blank.
    const payload: Record<string, any> = {};
    for (const [k, v] of Object.entries(values)) {
      if (v === "" || v === undefined || v === null) continue;
      payload[k] = v;
    }
    Object.assign(payload, uploads);
    try {
      await publicApi.post(
        `/api/forms/landlord-admin?token=${encodeURIComponent(token!)}`,
        payload,
      );
      setDone(true);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (Array.isArray(detail)) {
        const first = detail[0];
        setServerError(`${first?.loc?.join(".") ?? "field"}: ${first?.msg ?? "validation failed"}`);
      } else {
        setServerError(detail ?? "Submission failed");
      }
    }
  }

  if (tokenError) return <div className="card p-6 text-rose-700 bg-rose-50">{tokenError}</div>;
  if (!tokenInfo) return <div>Loading…</div>;
  if (done) {
    return (
      <div className="card p-10 text-center max-w-xl mx-auto">
        <div className="kicker">Submission received</div>
        <h2 className="mt-1">Thank you</h2>
        <p className="text-ink-soft mt-3">
          Your details have been received. We'll be in touch shortly with the next step (identity verification).
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      <header className="rounded-lg border border-cream-300 bg-white shadow-paper p-6 md:p-8"
        style={{ backgroundImage: "radial-gradient(600px 250px at 100% 0%, rgba(201, 162, 76, 0.07), transparent 60%)" }}>
        <div className="kicker">Stage 2 · Landlord onboarding</div>
        <h1 className="mt-1">Landlord admin form</h1>
        <p className="mt-3 text-ink-soft max-w-2xl">
          Please complete the sections below. Fields marked <span className="text-rose-600">*</span> are required.
        </p>
      </header>

      {/* ============================ Landlord identity (FIRST) ========== */}
      <Section title="Your information (Landlord)">
        <Field label="Full name" required error={errors.landlord_full_name?.message}>
          <input className="input" {...register("landlord_full_name", { required: "Required" })} />
        </Field>
        <Field label="Full address" required error={errors.landlord_full_address?.message}>
          <input className="input" {...register("landlord_full_address", { required: "Required" })} />
        </Field>
        <Field label="Post code" required>
          <input className="input" {...register("landlord_post_code", { required: "Required" })} />
        </Field>
        <Field label="Mobile number" required>
          <input className="input" {...register("landlord_mobile", { required: "Required" })} />
        </Field>
        <Field
          label="Email address"
          required
          hint="Prefilled from your invitation link. This is the address all communications from Palace Gate will go to.">
          <input className="input bg-cream-100" readOnly {...register("landlord_email", { required: "Required" })} />
        </Field>
      </Section>

      {/* ============================ Property ============================ */}
      <Section title="Property details">
        <Field label="Property postal code" required error={errors.property_post_code?.message}>
          <input className="input" {...register("property_post_code", { required: "Required" })} />
        </Field>
      </Section>

      {/* ============================ Block manager ====================== */}
      <Section
        title="Block manager (if applicable)"
        description="Only complete this if your building has a separate block manager. Leave blank if there isn't one. This is NOT your own contact information.">
        <Field label="Name"><input className="input" {...register("block_manager_name")} /></Field>
        <Field label="Address"><input className="input" {...register("block_manager_address")} /></Field>
        <Field label="Postal code"><input className="input" {...register("block_manager_postal_code")} /></Field>
        <Field label="Contact phone"><input className="input" {...register("block_manager_contact")} /></Field>
        <Field label="Email (block manager only — not your email)">
          <input className="input" type="email" {...register("block_manager_email")} />
        </Field>
      </Section>

      {/* ============================ Consents =========================== */}
      <Section title="Consent requirements">
        <Field label="Do you need consent to sub-let?">
          <select className="input" {...register("consent_sublet")}><option /><option>Yes</option><option>No</option></select>
        </Field>
        <Field label="Do you require consent from a mortgagor?">
          <select className="input" {...register("consent_mortgagor")}><option /><option>Yes</option><option>No</option></select>
        </Field>
        {consentMortgagor === "Yes" && (
          <PublicUpload
            token={token!} propertyId={tokenInfo.property_id}
            bucket="mortgage_consent"
            label="Upload your lender's consent to let letter"
            accept="application/pdf,image/*"
            value={uploads.mortgage_consent_upload}
            onChange={(u) => setUpload("mortgage_consent_upload", u)}
          />
        )}
      </Section>

      {/* ============================ Residency + Tax ==================== */}
      <Section title="Residency & tax">
        <Field label="Are you a UK resident or non-resident landlord?" required>
          <select className="input" {...register("residency", { required: "Required" })}>
            <option value="">—</option>
            <option>UK Resident</option>
            <option>Non-resident (overseas)</option>
          </select>
        </Field>

        <Field label="Do you have a Tax Exempt Number?">
          <select className="input" {...register("has_tax_exempt_number")}>
            <option /><option>Yes</option><option>No</option>
          </select>
        </Field>

        {/* has_tax_exempt_number = Yes → ask for the NRL number */}
        {hasTaxExempt === "Yes" && (
          <Field label="Add your NRL approval number">
            <input className="input" {...register("nrl_approval_number")} />
          </Field>
        )}

        {/* has_tax_exempt_number = No → ask whether they're applying */}
        {hasTaxExempt === "No" && (
          <Field label="Will you be applying to Inland Revenue for a Tax Exempt Number?">
            <select className="input" {...register("applying_for_nrl")}>
              <option /><option>Yes</option><option>No</option>
            </select>
          </Field>
        )}

        {/* applying_for_nrl = No → offer PG management */}
        {hasTaxExempt === "No" && applyingForNrl === "No" && (
          <Field label="Do you want Palace Gate to manage the tax-exempt number?">
            <select className="input" {...register("pg_manage_nrl")}>
              <option /><option>Yes</option><option>No</option>
            </select>
          </Field>
        )}

        <Field label="Will you appoint Palace Gate to pay tax (additional 2% fee)?">
          <select className="input" {...register("pg_collect_pay_tax")}>
            <option /><option>Yes</option><option>No</option>
          </select>
        </Field>

        <Field label="Will you appoint another agent (e.g. solicitor) to pay tax?">
          <select className="input" {...register("appoint_solicitor_for_tax")}>
            <option /><option>Yes</option><option>No</option>
          </select>
        </Field>

        {appointSolicitor === "Yes" && (
          <>
            <Field label="Tax agent — name"><input className="input" {...register("tax_agent_name")} /></Field>
            <Field label="Tax agent — address"><input className="input" {...register("tax_agent_address")} /></Field>
            <Field label="Tax agent — contact"><input className="input" {...register("tax_agent_contact")} /></Field>
          </>
        )}

        <Field label="If tenant pays rent directly, have you written to Inland Revenue asking them to authorise payment without withholding tax?">
          <select className="input" {...register("written_to_inland_revenue")}>
            <option /><option>Yes</option><option>No</option>
          </select>
        </Field>
      </Section>

      {/* ============================ Bank ================================ */}
      <Section title="Bank details for rental payments">
        <Field label="Bank name"><input className="input" {...register("bank_name")} /></Field>
        <Field label="Bank address"><input className="input" {...register("bank_address")} /></Field>
        <Field label="Sort code"><input className="input" {...register("sort_code")} /></Field>
        <Field label="Account name"><input className="input" {...register("account_name")} /></Field>
        <Field label="Account number"><input className="input" {...register("account_number")} /></Field>
      </Section>

      {/* ============================ Photos / inventory ================ */}
      <Section title="Photos & inventory">
        <Field label="Do you have photos and floorplans of the property?">
          <select className="input" {...register("has_photos")}><option /><option>Yes</option><option>No</option></select>
        </Field>
        {hasPhotos === "No" && (
          <Field label="Do you authorise Palace Gate to arrange photos/floorplans?">
            <select className="input" {...register("auth_photos")}><option /><option>Yes</option><option>No</option></select>
          </Field>
        )}
        <Field label="Do you have a current inventory for the contents?">
          <select className="input" {...register("has_inventory")}><option /><option>Yes</option><option>No</option></select>
        </Field>
        {hasInventory === "No" && (
          <Field label="Do you authorise Palace Gate to prepare an inventory?">
            <select className="input" {...register("auth_inventory")}><option /><option>Yes</option><option>No</option></select>
          </Field>
        )}
      </Section>

      {/* ============================ Property characteristics =========== */}
      <Section title="Property type & tenure">
        <Field label="What is the property type?">
          <select className="input" {...register("property_type")}>
            <option value="">—</option>
            <option>House</option>
            <option>Flat</option>
          </select>
        </Field>
        <Field label="Is the property leasehold or freehold?">
          <select className="input" {...register("tenure")}>
            <option value="">—</option>
            <option>Leasehold</option>
            <option>Freehold</option>
          </select>
        </Field>
        {tenure === "Leasehold" && (
          <>
            <Field label="What is the unexpired term?">
              <input className="input" {...register("unexpired_term")} />
            </Field>
            <Field label="What is the annual service charge (%)?">
              <input className="input" type="number" step="0.01" {...register("annual_service_charge", { valueAsNumber: true })} />
            </Field>
            <Field label="What is the ground rent per year (GBP)?">
              <input className="input" type="number" step="0.01" {...register("ground_rent", { valueAsNumber: true })} />
            </Field>
            <PublicUpload
              token={token!} propertyId={tokenInfo.property_id}
              bucket="head_lease"
              label="Head lease document"
              hint="PDF preferred — we'll skim for tenant-compliance restrictions."
              accept="application/pdf,image/*"
              value={uploads.head_lease_upload}
              onChange={(u) => setUpload("head_lease_upload", u)}
            />
            <Field label="Do you have freeholder consent to let?">
              <select className="input" {...register("freeholder_consent")}><option /><option>Yes</option><option>No</option></select>
            </Field>
            <PublicUpload
              token={token!} propertyId={tokenInfo.property_id}
              bucket="freeholder_consent"
              label="Upload the freeholder consent document"
              accept="application/pdf,image/*"
              value={uploads.freeholder_consent_upload}
              onChange={(u) => setUpload("freeholder_consent_upload", u)}
            />
          </>
        )}
      </Section>

      {/* ============================ Property management ================ */}
      <Section title="Property management">
        <Field label="Who will manage the property during tenancy?">
          <select className="input" {...register("who_manages_property")}>
            <option value="">—</option>
            {SERVICE_OPTIONS.map((o) => <option key={o}>{o}</option>)}
          </select>
        </Field>
        {showThirdPartyManager && (
          <Field label="If Other, provide name, address and contact details">
            <textarea className="input" rows={3} {...register("third_party_manager")} />
          </Field>
        )}
        <Field label="Is insurance already in place?">
          <select className="input" {...register("insurance_in_place")}><option /><option>Yes</option><option>No</option></select>
        </Field>
        {insuranceInPlace === "Yes" && (
          <>
            <Field label="Insurance provider name"><input className="input" {...register("insurance_provider")} /></Field>
            <Field label="Insurance policy number"><input className="input" {...register("insurance_policy_number")} /></Field>
            <PublicUpload
              token={token!} propertyId={tokenInfo.property_id}
              bucket="insurance_cert"
              label="Upload insurance certificate"
              accept="application/pdf,image/*"
              value={uploads.insurance_cert_upload}
              onChange={(u) => setUpload("insurance_cert_upload", u)}
            />
          </>
        )}
      </Section>

      {/* ============================ Utilities ========================== */}
      <Section title="Utilities information">
        <Field label="Telephone number, provider & account number">
          <textarea className="input" rows={2} {...register("telephone_provider_account")} />
        </Field>
        <Field label="Gas provider, account number & meter location">
          <textarea className="input" rows={2} {...register("gas_provider_meter")} />
        </Field>
        <Field label="Electricity provider, account number & meter location">
          <textarea className="input" rows={2} {...register("electricity_provider_meter")} />
        </Field>
        <Field label="Water provider & account number">
          <textarea className="input" rows={2} {...register("water_provider")} />
        </Field>
        <Field label="Cable TV details">
          <textarea className="input" rows={2} {...register("cable_tv_details")} />
        </Field>
        <Field label="Council tax borough">
          <textarea className="input" rows={2} {...register("council_tax_borough")} />
        </Field>
      </Section>

      <Section title="Utility locations in property">
        <Field label="Location of mains gas tap">
          <input className="input" {...register("gas_tap_location")} />
        </Field>
        <Field label="Location of water stop cock">
          <input className="input" {...register("water_stopcock_location")} />
        </Field>
        <Field label="Location of electricity main switch">
          <input className="input" {...register("electricity_main_switch")} />
        </Field>
        <Field label="Refuse collection day">
          <input className="input" {...register("refuse_collection_day")} />
        </Field>
      </Section>

      {/* ============================ Legal compliance ==================== */}
      <Section title="Legal compliance & certificates">
        <Field label="Do you have a current Gas Safety Certificate? (Legal Requirement)" required error={errors.has_gas_cert?.message}>
          <select className="input" {...register("has_gas_cert", { required: "Required" })}>
            <option value="" /><option>Yes</option><option>No</option>
          </select>
        </Field>
        {hasGas === "No" && (
          <Field label="If no, shall Palace Gate arrange the Gas Safety Certificate?">
            <select className="input" {...register("arrange_gas_cert")}><option /><option>Yes</option><option>No</option></select>
          </Field>
        )}
        {hasGas === "Yes" && (
          <>
            <Field label="Gas certificate expiry date">
              <input className="input" type="date" {...register("gas_cert_expiry")} />
            </Field>
            <PublicUpload
              token={token!} propertyId={tokenInfo.property_id}
              bucket="gas_cert"
              label="Upload Gas Safety Certificate"
              accept="application/pdf,image/*"
              value={uploads.gas_cert_upload}
              onChange={(u) => setUpload("gas_cert_upload", u)}
            />
          </>
        )}

        <Field label="Do you have a current EPC (Energy Performance Certificate)?" required error={errors.has_epc?.message}>
          <select className="input" {...register("has_epc", { required: "Required" })}>
            <option value="" /><option>Yes</option><option>No</option>
          </select>
        </Field>
        {hasEpc === "No" && (
          <Field label="If no, do you authorise Palace Gate to prepare the EPC?">
            <select className="input" {...register("arrange_epc")}><option /><option>Yes</option><option>No</option></select>
          </Field>
        )}
        {hasEpc === "Yes" && (
          <>
            <Field label="EPC rating">
              <select className="input" {...register("epc_rating")}>
                <option />{["A","B","C","D","E","F","G"].map((r) => <option key={r}>{r}</option>)}
              </select>
            </Field>
            <PublicUpload
              token={token!} propertyId={tokenInfo.property_id}
              bucket="epc"
              label="Upload EPC Certificate"
              accept="application/pdf,image/*"
              value={uploads.epc_upload}
              onChange={(u) => setUpload("epc_upload", u)}
            />
          </>
        )}

        <Field label="Do you have an EICR (Electrical Installation Condition Report)?" required error={errors.has_eicr?.message}>
          <select className="input" {...register("has_eicr", { required: "Required" })}>
            <option value="" /><option>Yes</option><option>No</option>
          </select>
        </Field>
        {hasEicr === "No" && (
          <Field label="If no, would you like Palace Gate to arrange the EICR?">
            <select className="input" {...register("arrange_eicr")}><option /><option>Yes</option><option>No</option></select>
          </Field>
        )}
        {hasEicr === "Yes" && (
          <>
            <Field label="EICR expiry date">
              <input className="input" type="date" {...register("eicr_expiry")} />
            </Field>
            <PublicUpload
              token={token!} propertyId={tokenInfo.property_id}
              bucket="eicr"
              label="Upload EICR report"
              accept="application/pdf,image/*"
              value={uploads.eicr_upload}
              onChange={(u) => setUpload("eicr_upload", u)}
            />
          </>
        )}

        <Field label="Have you fitted smoke detectors? (Legal Requirement)" required error={errors.smoke_detectors_fitted?.message}>
          <select className="input" {...register("smoke_detectors_fitted", { required: "Required" })}>
            <option value="" /><option>Yes</option><option>No</option>
          </select>
        </Field>
        <Field label="Does all upholstered furniture comply with Fire Regulations?">
          <select className="input" {...register("furniture_fire_regs")}>
            <option /><option>Yes</option><option>No</option>
          </select>
        </Field>
      </Section>

      {/* ============================ Access ============================= */}
      <Section title="Access arrangements">
        <Field label="Will you supply Palace Gate with a set of keys?">
          <select className="input" {...register("supply_keys")}><option /><option>Yes</option><option>No</option></select>
        </Field>
        {supplyKeys === "No" && (
          <Field label="If no, please confirm alternative access arrangements">
            <textarea className="input" rows={3} {...register("alternative_access")} />
          </Field>
        )}
      </Section>

      {serverError && <div className="card p-4 bg-rose-50 text-rose-700 border-rose-200">{serverError}</div>}

      <div className="flex justify-end">
        <button type="submit" className="btn-primary" disabled={isSubmitting}>
          {isSubmitting ? "Submitting…" : "Submit"}
        </button>
      </div>
    </form>
  );
}
