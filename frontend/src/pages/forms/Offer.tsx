import { useEffect, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";

import { BackLink } from "../../components/ui/BackLink";
import { Field, Section } from "../../components/ui/Field";
import { api } from "../../lib/api";

type FormValues = {
  tenant_full_name: string;
  tenant_email: string;
  tenant_address?: string;
  start_date: string;
  end_date?: string;
  tenancy_term?: string;
  monthly_rent: number;
  rent_frequency: "Monthly" | "Weekly";
  deposit_amount: number;
  holding_deposit: number;
  rent_in_advance_months: number;
  break_clause?: number;
  renewal_terms?: string;
  special_conditions?: string;
  number_of_occupants: number;
  guarantor_name?: string;
  guarantor_address?: string;
  guarantor_email?: string;
  is_student: boolean;
  anti_discrimination_confirmed: boolean;
  // Joint tenants who sign the same tenancy (maps to backend OfferInput.co_tenants).
  co_tenants: { full_name: string; email: string; address?: string; is_student: boolean }[];
};

export default function Offer() {
  const { id = "" } = useParams();
  const { register, handleSubmit, control, watch, setValue, formState: { errors, isSubmitting } } = useForm<FormValues>({
    defaultValues: {
      rent_frequency: "Monthly",
      rent_in_advance_months: 1,
      number_of_occupants: 1,
      is_student: false,
      anti_discrimination_confirmed: false,
      co_tenants: [],
    },
  });
  const { fields: coTenantFields, append: appendCoTenant, remove: removeCoTenant } =
    useFieldArray({ control, name: "co_tenants" });

  // Live HMO indicator: total = max(stated occupants, 1 lead + named co-tenants).
  // Mirrors the backend rule (HMO_Flag when total >= 3). Updates as the agent
  // adds/removes tenants or edits the occupant count.
  const statedOccupants = Number(watch("number_of_occupants")) || 1;
  const totalTenants = Math.max(statedOccupants, 1 + coTenantFields.length);
  const hmoTriggered = totalTenants >= 3;
  const [result, setResult] = useState<any>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const nav = useNavigate();

  // APT properties are periodic by law (RRA 2025) — the end-date field is
  // hidden for them so the offer can't be rejected by the APT gate after the
  // agent has filled the whole form in.
  const [tenancyType, setTenancyType] = useState<string | null>(null);
  const isApt = tenancyType === "APT";

  // Default rent_frequency from whatever was captured at take-on (PG_01).
  // In practice the offer's frequency almost always matches; the agent can
  // still override here if it doesn't.
  useEffect(() => {
    if (!id) return;
    api.get<{ fields: Record<string, any> }>(`/api/properties/${id}`)
      .then((r) => {
        const f = r.data?.fields?.["Rent Frequency"];
        if (f === "Monthly" || f === "Weekly") setValue("rent_frequency", f);
        setTenancyType(r.data?.fields?.["Tenancy Type"] ?? null);
      })
      .catch(() => { /* non-fatal — falls back to the hard-coded default */ });
  }, [id, setValue]);

  async function onSubmit(v: FormValues) {
    setServerError(null);
    // Strip empty strings AND NaN numbers (react-hook-form's valueAsNumber
    // emits NaN for blank inputs) so optional numeric fields like break_clause
    // don't 422 on the server.
    const body: Record<string, any> = {};
    for (const [k, val] of Object.entries(v)) {
      if (val === "" || val === undefined || val === null) continue;
      if (typeof val === "number" && Number.isNaN(val)) continue;
      body[k] = val;
    }
    body.monthly_rent = Number(v.monthly_rent);
    body.deposit_amount = Number(v.deposit_amount);
    // Holding deposit is optional — omit entirely when blank rather than
    // coercing to 0, so "none was taken" is stored as empty, not £0.00.
    if (v.holding_deposit === undefined || v.holding_deposit === null || String(v.holding_deposit) === "") {
      delete body.holding_deposit;
    } else {
      body.holding_deposit = Number(v.holding_deposit);
    }
    body.rent_in_advance_months = Number(v.rent_in_advance_months);
    body.number_of_occupants = Number(v.number_of_occupants);
    // Safety net: an APT offer is periodic — never submit an end date.
    if (isApt) delete body.end_date;
    // Keep only fully-filled co-tenant rows — the backend CoTenantInput requires
    // name + email, so a blank/partial row would 422.
    const coTenants = (v.co_tenants ?? []).filter(
      (ct) => ct?.full_name?.trim() && ct?.email?.trim(),
    );
    if (coTenants.length) body.co_tenants = coTenants;
    else delete body.co_tenants;
    try {
      const { data } = await api.post(`/api/forms/offer/${id}`, body);
      setResult(data);
      if (!data.violations?.length) {
        setTimeout(() => nav(`/agent/properties/${id}`), 1200);
      }
    } catch (e: any) {
      setServerError(e?.response?.data?.detail ?? "Submission failed");
    }
  }

  return (
    <form className="space-y-6" onSubmit={handleSubmit(onSubmit)}>
      <header className="rounded-lg border border-cream-300 bg-white shadow-paper p-6 md:p-8"
        style={{ backgroundImage: "radial-gradient(600px 250px at 100% 0%, rgba(201, 162, 76, 0.07), transparent 60%)" }}>
        <BackLink to={`/agent/properties/${id}`} label="Property" />
        <div className="kicker mt-2">Stage 4 · Tenant offer</div>
        <h1 className="mt-1">Record offer</h1>
        <p className="mt-3 text-ink-soft max-w-2xl">
          APT properties are auto-validated (holding deposit ≤ 1 week rent, rent in advance ≤ 1 month).
        </p>
      </header>

      <Section title="Tenant">
        <Field label="Tenant full name" required error={errors.tenant_full_name?.message}>
          <input className="input" {...register("tenant_full_name", { required: "Required" })} />
        </Field>
        <Field label="Tenant email" required error={errors.tenant_email?.message}>
          <input className="input" type="email" {...register("tenant_email", { required: "Required" })} />
        </Field>
        <Field label="Tenant address (optional)">
          <input className="input" {...register("tenant_address")} />
        </Field>
        <Field label="Is student?">
          <label className="flex items-center gap-2"><input type="checkbox" {...register("is_student")} /> Yes</label>
        </Field>
      </Section>

      <Section
        title="Additional tenants (joint tenancy)"
        description="Add anyone else who will sign the same tenancy. Each becomes a referenced tenant on the property; the lead tenant above is included automatically. 3+ total triggers the HMO flag.">
        {coTenantFields.length === 0 && (
          <p className="text-sm text-ink-muted">No additional tenants — the lead tenant above is the sole tenant.</p>
        )}
        <div className="space-y-4">
          {coTenantFields.map((row, i) => (
            <div key={row.id} className="rounded-lg border border-cream-300 p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs uppercase tracking-wide text-slate-500">Tenant {i + 2}</span>
                <button type="button" className="text-xs text-rose-600 hover:underline" onClick={() => removeCoTenant(i)}>
                  Remove
                </button>
              </div>
              <div className="grid sm:grid-cols-2 gap-3">
                <Field label="Full name" required error={errors.co_tenants?.[i]?.full_name?.message}>
                  <input className="input" {...register(`co_tenants.${i}.full_name` as const, { required: "Required" })} />
                </Field>
                <Field label="Email" required error={errors.co_tenants?.[i]?.email?.message}>
                  <input className="input" type="email" {...register(`co_tenants.${i}.email` as const, { required: "Required" })} />
                </Field>
                <Field label="Address (optional)">
                  <input className="input" {...register(`co_tenants.${i}.address` as const)} />
                </Field>
                <Field label="Is student?">
                  <label className="flex items-center gap-2">
                    <input type="checkbox" {...register(`co_tenants.${i}.is_student` as const)} /> Yes
                  </label>
                </Field>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between gap-3 flex-wrap">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => appendCoTenant({ full_name: "", email: "", address: "", is_student: false })}>
            + Add tenant
          </button>
          <span className="text-xs text-ink-muted">
            {totalTenants} tenant{totalTenants === 1 ? "" : "s"} / occupant{totalTenants === 1 ? "" : "s"} total
          </span>
        </div>
        {hmoTriggered && (
          <div className="mt-3 flex items-start gap-2.5 rounded-lg border border-amber-300 bg-amber-50 p-3 text-amber-900">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" className="mt-0.5 shrink-0" aria-hidden="true">
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <div className="text-sm">
              <strong>HMO licence required.</strong> {totalTenants} tenants/occupants (3 or more) means this is a
              House in Multiple Occupation. On submit the property is flagged <code>HMO</code> and a critical
              “Confirm HMO licence” checklist item is added — the offer can’t advance to move-in until it’s confirmed.
            </div>
          </div>
        )}
      </Section>

      <Section title="Tenancy">
        <Field label="Start date" required>
          <input className="input" type="date" {...register("start_date", { required: "Required" })} />
        </Field>
        {isApt ? (
          <Field label="End date" hint="Assured periodic tenancies are open-ended under the Renters' Rights Act 2025 — no end date applies.">
            <div className="rounded-lg border border-cream-300 bg-cream-100 px-3 py-2 text-sm text-ink-soft">
              Periodic tenancy — runs month to month with no fixed end date.
            </div>
          </Field>
        ) : (
          <Field label="End date" hint="Leave blank for a periodic tenancy">
            <input className="input" type="date" {...register("end_date")} />
          </Field>
        )}
        <Field label="Tenancy term (e.g. 12 months)">
          <input className="input" {...register("tenancy_term")} />
        </Field>
        <Field label="Break clause fee (£)" hint="Optional fee (£) payable if the tenant activates a break clause — it appears in the tenancy agreement. Leave blank if the tenancy has no break clause.">
          <input className="input" type="number" step="0.01" {...register("break_clause", { valueAsNumber: true })} />
        </Field>
        <Field label="Renewal terms">
          <input className="input" {...register("renewal_terms")} />
        </Field>
        <Field label="Number of occupants" hint="3+ triggers HMO flag">
          <input className="input" type="number" min={1} {...register("number_of_occupants")} />
        </Field>
        <Field label="Special conditions">
          <input className="input" {...register("special_conditions")} />
        </Field>
      </Section>

      <Section title="Money">
        <Field label="Monthly rent (£)" required>
          <input className="input" type="number" step="0.01" {...register("monthly_rent", { required: "Required" })} />
        </Field>
        <Field label="Rent frequency">
          <select className="input" {...register("rent_frequency")}>
            <option value="Monthly">Monthly</option>
            <option value="Weekly">Weekly</option>
          </select>
        </Field>
        <Field label="Deposit amount (£)" required>
          <input className="input" type="number" step="0.01" {...register("deposit_amount", { required: "Required" })} />
        </Field>
        <Field label="Holding deposit (£)" hint="Optional — leave blank if no holding deposit was taken. If one was, it can be at most 1 week's rent (Tenant Fees Act 2019).">
          <input className="input" type="number" step="0.01" {...register("holding_deposit")} />
        </Field>
        <Field label="Rent in advance (months)">
          <input className="input" type="number" min={0} {...register("rent_in_advance_months")} />
        </Field>
      </Section>

      <Section title="Guarantor (optional)">
        <Field label="Guarantor name"><input className="input" {...register("guarantor_name")} /></Field>
        <Field label="Guarantor email"><input className="input" type="email" {...register("guarantor_email")} /></Field>
        <Field label="Guarantor address"><input className="input" {...register("guarantor_address")} /></Field>
      </Section>

      <Section
        title="Compliance"
        description="Required confirmations before the offer can be recorded.">
        <Field label="Equality Act 2010" hint="Confirm no prospective tenant was rejected on a protected ground. Recorded with today's date.">
          <label className="flex items-start gap-2 cursor-pointer p-2 -ml-2 rounded hover:bg-cream-100">
            <input type="checkbox" className="mt-1" {...register("anti_discrimination_confirmed")} />
            <span className="text-sm text-ink-soft">
              I confirm anti-discrimination requirements have been met for this letting.
            </span>
          </label>
        </Field>
      </Section>

      {serverError && <div className="card p-4 bg-rose-50 text-rose-700 border-rose-200">{serverError}</div>}
      {result?.violations?.length > 0 && (
        <div className="card p-4 bg-rose-50 text-rose-700 border-rose-200">
          <strong>APT violations — offer NOT recorded:</strong>
          <ul className="list-disc ml-5 mt-2">{result.violations.map((v: string, i: number) => <li key={i}>{v}</li>)}</ul>
        </div>
      )}
      {result && !result.violations?.length && (
        <div className="card p-4 bg-emerald-50 text-emerald-800 border-emerald-200">
          Offer recorded. DocuSeal Offer Letter created. Redirecting…
        </div>
      )}

      <div className="flex justify-end">
        <button type="submit" className="btn-primary" disabled={isSubmitting}>
          {isSubmitting ? "Submitting…" : "Submit offer"}
        </button>
      </div>
    </form>
  );
}
