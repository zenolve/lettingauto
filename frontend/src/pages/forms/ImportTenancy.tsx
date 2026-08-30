import { useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";

import { BackLink } from "../../components/ui/BackLink";
import { Field, Section } from "../../components/ui/Field";
import { api } from "../../lib/api";

type TenantRow = { full_name: string; email: string };

type FormValues = {
  address: string;
  post_code: string;
  property_type: string;
  landlord_full_name: string;
  landlord_email: string;
  landlord_full_address: string;
  landlord_post_code: string;
  landlord_mobile: string;
  residency: "" | "UK Resident" | "Non-resident (overseas)";
  nrl_approval_number: string;
  bank_name: string;
  sort_code: string;
  account_name: string;
  account_number: string;
  smoke_detectors_fitted: "" | "Yes" | "No";
  furniture_fire_regs: "" | "Yes" | "No";
  tenants: TenantRow[];
  /** Index of the lead tenant — mapped onto is_lead when submitting. */
  lead_index: number;
  guarantor_name: string;
  guarantor_email: string;
  rent_amount: number;
  rent_frequency: "Monthly" | "Weekly";
  start_date: string;
  end_date: string;
  deposit_amount: string;
  tenancy_type: "" | "APT" | "Common Law";
  service_level: "" | "Full Management" | "Rent Collection" | "Let Only";
  gas_cert_expiry: string;
  epc_rating: string;
  eicr_expiry: string;
  hmo_licence_confirmed: boolean;
  deposit_registered: boolean;
  deposit_registration_date: string;
  tds_cert_on_file: boolean;
  tc_signed: boolean;
  ta_landlord_signed: boolean;
  ta_tenants_signed: boolean;
  how_to_rent_served: boolean;
  gas_cert_served: boolean;
  epc_served: boolean;
  eicr_served: boolean;
  tds_info_served: boolean;
  rra_sheet_served: boolean;
  notes: string;
};

type Compliance = { warnings: string[]; actions: string[]; flags: string[] };

type ImportResult = {
  property_id: string;
  compliance?: Compliance;
  stage_reached: number;
  blocked_at: number | null;
  blockers: string[];
  is_live: boolean;
};

/**
 * Import an already-running tenancy.
 *
 * Every tick below is an assertion that something already happened offline.
 * They map onto the same flags the stage gates read, so the tenancy advances
 * on its own merits — an import with gaps stops where the evidence runs out
 * and says why, rather than silently landing as "Live".
 */
export default function ImportTenancy() {
  const { register, handleSubmit, control, watch, formState: { errors, isSubmitting } } =
    useForm<FormValues>({
      defaultValues: {
        rent_frequency: "Monthly",
        tenancy_type: "",
        service_level: "",
        lead_index: 0,
        residency: "",
        smoke_detectors_fitted: "",
        furniture_fire_regs: "",
        tenants: [{ full_name: "", email: "" }],
      },
    });
  const { fields, append, remove } = useFieldArray({ control, name: "tenants" });
  const [serverError, setServerError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const nav = useNavigate();

  const depositRegistered = watch("deposit_registered");

  async function onSubmit(v: FormValues) {
    setServerError(null);
    try {
      const { data } = await api.post<ImportResult>("/api/forms/import-tenancy", {
        ...v,
        tenancy_type: v.tenancy_type || null,
        service_level: v.service_level || null,
        residency: v.residency || null,
        smoke_detectors_fitted: v.smoke_detectors_fitted || null,
        furniture_fire_regs: v.furniture_fire_regs || null,
        deposit_amount: v.deposit_amount === "" ? null : Number(v.deposit_amount),
        rent_amount: Number(v.rent_amount),
        tenants: v.tenants
          .map((t, i) => ({ ...t, is_lead: i === Number(v.lead_index) }))
          .filter((t) => t.full_name.trim()),
      });
      setResult(data);
    } catch (e: any) {
      const d = e?.response?.data?.detail;
      setServerError(typeof d === "string" ? d : d ? JSON.stringify(d) : "Import failed");
    }
  }

  // --- Result screen -------------------------------------------------------
  if (result) {
    return (
      <div className="max-w-3xl space-y-4">
        <h1 className="font-serif text-2xl font-semibold text-navy-700">Tenancy imported</h1>

        {result.is_live ? (
          <div className="card p-5 bg-emerald-50 border-emerald-200">
            <p className="text-sm text-emerald-900">
              <strong>Live tenancy.</strong> Everything the pipeline checks was satisfied, so this
              tenancy went all the way to Stage 8 and is now managed like any other.
            </p>
          </div>
        ) : (
          <div className="card p-5 bg-amber-50 border-amber-200">
            <p className="text-sm text-amber-900">
              <strong>Imported to Stage {result.stage_reached}</strong> — it stopped before Live
              because Stage {result.blocked_at} needs evidence this tenancy doesn't have yet:
            </p>
            <ul className="mt-2 space-y-1">
              {result.blockers.map((b, i) => (
                <li key={i} className="text-sm text-amber-900">• {b}</li>
              ))}
            </ul>
            <p className="text-xs text-amber-800 mt-3">
              This isn't a failed import — the records exist and the tenancy is managed from
              Stage {result.stage_reached}. Resolve the items above on the property and re-run the
              gate to move it to Live.
            </p>
          </div>
        )}

        {(result.compliance?.warnings?.length || result.compliance?.actions?.length) ? (
          <div className="card p-5 border-l-4 border-l-rose-400">
            <h3 className="font-serif text-base font-semibold text-navy-700">
              Compliance findings on this tenancy
            </h3>
            <p className="text-xs text-ink-muted mt-1">
              Found by running the same checks a new tenancy gets. These describe the tenancy as it
              stands today — they aren't import errors.
            </p>
            {result.compliance?.warnings?.length ? (
              <ul className="mt-3 space-y-1">
                {result.compliance.warnings.map((w, i) => (
                  <li key={i} className="text-sm text-rose-800">• {w}</li>
                ))}
              </ul>
            ) : null}
            {result.compliance?.actions?.length ? (
              <ul className="mt-3 space-y-1">
                {result.compliance.actions.map((a, i) => (
                  <li key={i} className="text-sm text-amber-800">• {a}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <div className="card p-5">
          <h3 className="font-serif text-base font-semibold text-navy-700">Attach the paperwork</h3>
          <p className="text-sm text-ink-muted mt-1">
            The agreements were signed elsewhere, so upload the executed copies against this
            property — the signed tenancy agreement, terms of business, certificates and the
            deposit protection certificate.
          </p>
          <div className="flex gap-2 mt-4">
            <button className="btn-primary" onClick={() => nav(`/agent/properties/${result.property_id}/uploads`)}>
              Upload documents →
            </button>
            <button className="btn-secondary" onClick={() => nav(`/agent/properties/${result.property_id}`)}>
              Open property
            </button>
          </div>
        </div>

        <button className="btn-ghost text-sm" onClick={() => { setResult(null); }}>
          Import another tenancy
        </button>
      </div>
    );
  }

  // --- Form ----------------------------------------------------------------
  return (
    <form onSubmit={handleSubmit(onSubmit)} className="max-w-4xl space-y-5">
      <div>
        <BackLink to="/agent/properties" label="Properties" />
        <h1 className="font-serif text-2xl font-semibold text-navy-700 mt-1">Import an existing tenancy</h1>
        <p className="text-sm text-ink-muted">
          For a tenancy that's already running and was set up elsewhere. Nothing is emailed to the
          landlord or tenants — this records history, it doesn't re-run it.
        </p>
      </div>

      <Section title="Property" description="Where the tenancy is.">
        <Field label="Address" required error={errors.address?.message}>
          <input className="input" {...register("address", { required: "Address is required" })} />
        </Field>
        <Field label="Postcode" required error={errors.post_code?.message}>
          <input className="input" {...register("post_code", { required: "Postcode is required" })} />
        </Field>
        <Field label="Property type" hint="e.g. 2-bed flat">
          <input className="input" {...register("property_type")} />
        </Field>
        <Field label="Service level">
          <select className="input" {...register("service_level")}>
            <option value="">—</option>
            <option>Full Management</option>
            <option>Rent Collection</option>
            <option>Let Only</option>
          </select>
        </Field>
      </Section>

      <Section title="Landlord">
        <Field label="Full name" required error={errors.landlord_full_name?.message}>
          <input className="input" {...register("landlord_full_name", { required: "Required" })} />
        </Field>
        <Field label="Email" required error={errors.landlord_email?.message}>
          <input className="input" type="email" {...register("landlord_email", { required: "Required" })} />
        </Field>
        <Field label="Correspondence address"
               hint="Deposit prescribed information must carry the landlord's address">
          <input className="input" {...register("landlord_full_address")} />
        </Field>
        <Field label="Landlord postcode">
          <input className="input" {...register("landlord_post_code")} />
        </Field>
        <Field label="Mobile">
          <input className="input" {...register("landlord_mobile")} />
        </Field>
      </Section>

      <Section title="Residency & tax"
               description="A non-resident landlord without an HMRC approval number means 20% withholding applies. Left blank this defaults to UK resident, so an overseas landlord would be taxed incorrectly.">
        <Field label="UK resident or non-resident?">
          <select className="input" {...register("residency")}>
            <option value="">—</option>
            <option>UK Resident</option>
            <option>Non-resident (overseas)</option>
          </select>
        </Field>
        <Field label="NRL approval number" hint="If HMRC has approved gross rent">
          <input className="input" {...register("nrl_approval_number")} />
        </Field>
      </Section>

      <Section title="Landlord payout"
               description="Needed to disburse rent under Full Management or Rent Collection.">
        <Field label="Bank name"><input className="input" {...register("bank_name")} /></Field>
        <Field label="Account name"><input className="input" {...register("account_name")} /></Field>
        <Field label="Sort code"><input className="input" placeholder="00-00-00" {...register("sort_code")} /></Field>
        <Field label="Account number"><input className="input" {...register("account_number")} /></Field>
      </Section>

      <section className="card p-6 md:p-7 space-y-4">
        <header className="border-b border-cream-300 pb-3">
          <h3 className="font-serif text-lg font-semibold text-navy-700">Tenants</h3>
          <p className="text-sm text-ink-muted mt-1">
            Everyone named on the agreement. The lead tenant receives any correspondence.
          </p>
        </header>
        {fields.map((f, i) => (
          <div key={f.id} className="grid gap-3 md:grid-cols-[1fr_1fr_auto_auto] items-end">
            <Field label={`Tenant ${i + 1} name`} required>
              <input className="input" {...register(`tenants.${i}.full_name` as const, { required: true })} />
            </Field>
            <Field label="Email">
              <input className="input" type="email" {...register(`tenants.${i}.email` as const)} />
            </Field>
            <label className="flex items-center gap-2 text-sm text-ink-soft pb-2"
                   title="The lead tenant receives correspondence about this tenancy">
              <input type="radio" value={i} {...register("lead_index")} />
              Lead
            </label>
            {fields.length > 1 && (
              <button type="button" className="btn-ghost text-sm pb-2" onClick={() => remove(i)}>Remove</button>
            )}
          </div>
        ))}
        <button type="button" className="btn-ghost text-sm"
                onClick={() => append({ full_name: "", email: "" })}>
          + add tenant
        </button>
        <div className="grid gap-4 md:grid-cols-2 pt-2 border-t border-cream-300">
          <Field label="Guarantor name" hint="Leave blank if there isn't one">
            <input className="input" {...register("guarantor_name")} />
          </Field>
          <Field label="Guarantor email">
            <input className="input" type="email" {...register("guarantor_email")} />
          </Field>
        </div>
      </section>

      <Section title="Tenancy terms" description="As they stand on the signed agreement.">
        <Field label="Rent amount" required error={errors.rent_amount?.message}>
          <input className="input" type="number" step="0.01"
                 {...register("rent_amount", { required: "Required", min: { value: 0.01, message: "Must be positive" } })} />
        </Field>
        <Field label="Rent frequency">
          <select className="input" {...register("rent_frequency")}>
            <option>Monthly</option>
            <option>Weekly</option>
          </select>
        </Field>
        <Field label="Start date" required error={errors.start_date?.message}>
          <input className="input" type="date" {...register("start_date", { required: "Required" })} />
        </Field>
        <Field label="End date" hint="Leave blank if periodic">
          <input className="input" type="date" {...register("end_date")} />
        </Field>
        <Field label="Deposit held (£)">
          <input className="input" type="number" step="0.01" {...register("deposit_amount")} />
        </Field>
        <Field label="Tenancy type" hint="Leave as derive — set from the annual rent">
          <select className="input" {...register("tenancy_type")}>
            <option value="">Derive from rent</option>
            <option value="APT">APT</option>
            <option value="Common Law">Common Law</option>
          </select>
        </Field>
      </Section>

      <Section title="Compliance certificates"
               description="Expiry dates drive the renewal reminders, so they're worth getting right.">
        <Field label="Gas certificate expiry">
          <input className="input" type="date" {...register("gas_cert_expiry")} />
        </Field>
        <Field label="EICR expiry">
          <input className="input" type="date" {...register("eicr_expiry")} />
        </Field>
        <Field label="EPC rating">
          <input className="input" {...register("epc_rating")} />
        </Field>
        <label className="flex items-center gap-2 text-sm text-ink-soft self-end pb-2">
          <input type="checkbox" {...register("hmo_licence_confirmed")} /> HMO licence confirmed
        </label>
        <Field label="Smoke detectors fitted?">
          <select className="input" {...register("smoke_detectors_fitted")}>
            <option value="">—</option><option>Yes</option><option>No</option>
          </select>
        </Field>
        <Field label="Furniture meets fire regulations?">
          <select className="input" {...register("furniture_fire_regs")}>
            <option value="">—</option><option>Yes</option><option>No</option>
          </select>
        </Field>
      </Section>

      <Section title="Deposit protection">
        <label className="flex items-center gap-2 text-sm text-ink-soft">
          <input type="checkbox" {...register("deposit_registered")} /> Deposit registered with a scheme
        </label>
        <label className="flex items-center gap-2 text-sm text-ink-soft">
          <input type="checkbox" {...register("tds_cert_on_file")} /> Scheme certificate on file
        </label>
        {depositRegistered && (
          <Field label="Date registered" hint="The 30-day clock ran from receipt of the deposit">
            <input className="input" type="date" {...register("deposit_registration_date")} />
          </Field>
        )}
      </Section>

      <section className="card p-6 md:p-7 space-y-3">
        <header className="border-b border-cream-300 pb-3">
          <h3 className="font-serif text-lg font-semibold text-navy-700">Already signed and served</h3>
          <p className="text-sm text-ink-muted mt-1">
            Tick only what genuinely happened. These are the same checks the pipeline applies to a
            new tenancy — anything left unticked will hold the import short of Live and be listed
            for you, which is usually more useful than finding out later.
          </p>
        </header>
        <div className="grid gap-2 md:grid-cols-2">
          {([
            ["tc_signed", "Terms of business signed by landlord"],
            ["ta_landlord_signed", "Tenancy agreement signed by landlord"],
            ["ta_tenants_signed", "Tenancy agreement signed by all tenants"],
            ["how_to_rent_served", "How to Rent guide served"],
            ["gas_cert_served", "Gas certificate served on tenant"],
            ["epc_served", "EPC served on tenant"],
            ["eicr_served", "EICR served on tenant"],
            ["tds_info_served", "Deposit prescribed information served"],
            ["rra_sheet_served", "RRA information sheet served (APT)"],
          ] as const).map(([name, label]) => (
            <label key={name} className="flex items-center gap-2 text-sm text-ink-soft">
              <input type="checkbox" {...register(name)} /> {label}
            </label>
          ))}
        </div>
      </section>

      <Section title="Notes">
        <div className="md:col-span-2">
          <textarea className="input w-full h-24" placeholder="Anything worth recording about this tenancy"
                    {...register("notes")} />
        </div>
      </Section>

      {serverError && (
        <div className="card p-4 bg-rose-50 border-rose-200 text-rose-700 text-sm">{serverError}</div>
      )}

      <div className="flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={() => nav("/agent/properties")}>Cancel</button>
        <button className="btn-primary" disabled={isSubmitting}>
          {isSubmitting ? "Importing…" : "Import tenancy"}
        </button>
      </div>
    </form>
  );
}
