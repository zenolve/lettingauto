import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";

import { BackLink } from "../../components/ui/BackLink";
import { Field, Section } from "../../components/ui/Field";
import { api } from "../../lib/api";

type FormValues = {
  address: string;
  post_code: string;
  landlord_full_name: string;
  landlord_email: string;
  asking_rent_pcm: number;
  rent_frequency: "Monthly" | "Weekly";
  send_admin_form: boolean;
};

export default function PropertyTakeon() {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormValues>({
    defaultValues: { send_admin_form: true, rent_frequency: "Monthly" },
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const nav = useNavigate();

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      const { data } = await api.post("/api/forms/property-takeon", {
        ...values,
        asking_rent_pcm: values.asking_rent_pcm ? Number(values.asking_rent_pcm) : undefined,
      });
      nav(`/agent/properties/${data.property_id}`);
    } catch (e: any) {
      setServerError(e?.response?.data?.detail ?? "Submission failed");
    }
  }

  return (
    <form className="space-y-6" onSubmit={handleSubmit(onSubmit)}>
      <header className="rounded-lg border border-cream-300 bg-white shadow-paper p-6 md:p-8"
        style={{ backgroundImage: "radial-gradient(600px 250px at 100% 0%, rgba(201, 162, 76, 0.07), transparent 60%)" }}>
        <BackLink to="/agent" label="Dashboard" />
        <div className="kicker mt-2">Stage 1 · Property take-on</div>
        <h1 className="mt-1">New property</h1>
        <p className="mt-3 text-ink-soft max-w-2xl">
          Creates the property and landlord stub, then emails the landlord a link to the admin form.
        </p>
      </header>

      <Section title="Property">
        <Field label="Property address" required error={errors.address?.message}>
          <input className="input" {...register("address", { required: "Address is required" })} />
        </Field>
        <Field label="Postcode" required error={errors.post_code?.message}>
          <input className="input" {...register("post_code", { required: "Postcode is required" })} />
        </Field>
        <Field label="Rent frequency">
          <select className="input" {...register("rent_frequency")}>
            <option value="Monthly">Monthly</option>
            <option value="Weekly">Weekly</option>
          </select>
        </Field>
        <Field label="Asking rent" hint="One payment at the chosen frequency. Annualised internally to set APT vs Common Law.">
          <input className="input" type="number" step="0.01" {...register("asking_rent_pcm")} />
        </Field>
      </Section>

      <Section title="Landlord">
        <Field label="Landlord full name" required error={errors.landlord_full_name?.message}>
          <input className="input" {...register("landlord_full_name", { required: "Name is required" })} />
        </Field>
        <Field label="Landlord email" required error={errors.landlord_email?.message}>
          <input
            className="input"
            type="email"
            {...register("landlord_email", { required: "Email is required" })}
          />
        </Field>
        <Field label="Send admin form?" hint="Email the landlord a link to complete onboarding">
          <label className="flex items-center gap-2">
            <input type="checkbox" {...register("send_admin_form")} />
            <span className="text-sm">Yes, send now</span>
          </label>
        </Field>
      </Section>

      {serverError && <div className="card p-4 bg-rose-50 text-rose-700 border-rose-200">{serverError}</div>}

      <div className="flex justify-end gap-2">
        <button type="submit" className="btn-primary" disabled={isSubmitting}>
          {isSubmitting ? "Creating…" : "Create property"}
        </button>
      </div>
    </form>
  );
}
