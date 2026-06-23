import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router-dom";

import { BackLink } from "../../components/ui/BackLink";
import { Field, Section } from "../../components/ui/Field";
import { api } from "../../lib/api";
import { useAgency } from "../../lib/agency";

type FormValues = {
  address: string;
  post_code: string;
  landlord_full_name: string;
  landlord_email: string;
  asking_rent_pcm: number;
  rent_frequency: "Monthly" | "Weekly";
  send_admin_form: boolean;
  agent_email: string;
};

export default function PropertyTakeon() {
  const { register, handleSubmit, watch, setValue, formState: { errors, isSubmitting } } = useForm<FormValues>({
    defaultValues: { send_admin_form: true, rent_frequency: "Monthly" },
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const nav = useNavigate();

  // When "send to landlord" is off, the onboarding form goes to the agent.
  // Default the recipient to the logged-in agent's email (editable in the form).
  const agentEmail = useAgency((s) => s.agency?.membership.email);
  const sendToLandlord = watch("send_admin_form");
  useEffect(() => {
    if (agentEmail) setValue("agent_email", agentEmail);
  }, [agentEmail, setValue]);

  // Pay-first: if the agent abandoned a previous checkout, Stripe sends them
  // back here with ?payment=cancelled&payment_id=… — nothing was created.
  // While the session is still payable (~24h) we offer to resume it.
  const [search] = useSearchParams();
  const cancelled = search.get("payment") === "cancelled";
  const cancelledPaymentId = search.get("payment_id");
  const [resumeUrl, setResumeUrl] = useState<string | null>(null);
  useEffect(() => {
    if (cancelled && cancelledPaymentId) {
      api.get(`/api/forms/takeon-status/${cancelledPaymentId}`)
        .then((r) => { if (r.data.status === "pending") setResumeUrl(r.data.checkout_url); })
        .catch(() => undefined);
    }
  }, [cancelled, cancelledPaymentId]);

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      const { data } = await api.post("/api/forms/property-takeon", {
        ...values,
        asking_rent_pcm: values.asking_rent_pcm ? Number(values.asking_rent_pcm) : undefined,
      });
      // Pay-first: with billing on, nothing exists yet — the backend stored
      // the form as an intent and we go to Stripe. The property is created
      // only after payment confirms (TakeonComplete polls for it). With
      // billing off (dev), the property is created immediately.
      if (data.payment_required && data.checkout_url) {
        window.location.assign(data.checkout_url);
        return;
      }
      nav(`/agent/properties/${data.property_id}`);
    } catch (e: any) {
      setServerError(e?.response?.data?.detail ?? "Submission failed");
    }
  }

  return (
    <form className="space-y-6" onSubmit={handleSubmit(onSubmit)}>
      <header className="card bg-mesh-corner p-6 md:p-8">
        <BackLink to="/agent" label="Dashboard" />
        <div className="kicker mt-2">Stage 1 · Property take-on</div>
        <h1 className="mt-1">New property</h1>
        <p className="mt-3 text-ink-soft max-w-2xl">
          You'll pay the one-time £50 setup fee via Stripe first; the property and landlord
          records are created (and the landlord emailed) the moment payment confirms.
        </p>
      </header>

      {cancelled && (
        <div className="card p-4 bg-amber-50 border-amber-200 text-amber-800 flex flex-wrap items-center justify-between gap-3">
          <span className="text-sm">
            Payment was cancelled — <strong>no property was created</strong> and nothing was charged.
          </span>
          {resumeUrl && (
            <button type="button" className="btn-primary text-sm"
              onClick={() => window.location.assign(resumeUrl)}>
              Resume payment
            </button>
          )}
        </div>
      )}

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
        <Field label="Send admin form to landlord?" hint="If off, we email the onboarding link to you (the agent) instead of the landlord">
          <label className="flex items-center gap-2">
            <input type="checkbox" {...register("send_admin_form")} />
            <span className="text-sm">Yes, email the landlord</span>
          </label>
        </Field>
        {!sendToLandlord && (
          <Field
            label="Send onboarding form to"
            hint="Defaults to your email. Change it to send the admin + verification links to a different address."
            error={errors.agent_email?.message}
          >
            <input
              className="input"
              type="email"
              {...register("agent_email", {
                required: "An email is required when not sending to the landlord",
              })}
            />
          </Field>
        )}
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
