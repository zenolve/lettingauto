import { useState } from "react";
import { useForm } from "react-hook-form";
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
};

export default function Offer() {
  const { id = "" } = useParams();
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormValues>({
    defaultValues: {
      rent_frequency: "Monthly",
      rent_in_advance_months: 1,
      number_of_occupants: 1,
      is_student: false,
      anti_discrimination_confirmed: false,
    },
  });
  const [result, setResult] = useState<any>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const nav = useNavigate();

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
    body.holding_deposit = Number(v.holding_deposit);
    body.rent_in_advance_months = Number(v.rent_in_advance_months);
    body.number_of_occupants = Number(v.number_of_occupants);
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

      <Section title="Tenancy">
        <Field label="Start date" required>
          <input className="input" type="date" {...register("start_date", { required: "Required" })} />
        </Field>
        <Field label="End date" hint="Leave blank for APT/periodic">
          <input className="input" type="date" {...register("end_date")} />
        </Field>
        <Field label="Tenancy term (e.g. 12 months)">
          <input className="input" {...register("tenancy_term")} />
        </Field>
        <Field label="Break clause fee (£)" hint="Optional fee charged if the tenant exercises a break clause. Leave blank if none.">
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
        <Field label="Holding deposit (£)" required>
          <input className="input" type="number" step="0.01" {...register("holding_deposit", { required: "Required" })} />
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
