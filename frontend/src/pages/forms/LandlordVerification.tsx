import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";

import { Field, Section } from "../../components/ui/Field";
import { PublicUpload } from "../../components/ui/PublicUpload";
import { publicApi } from "../../lib/api";

type Form = {
  individual_or_company: "Individual" | "Company";
  residency: string;
  id_document_type?: string;
  id_document_upload?: string;
  visa_snapshot?: string;
  address_doc_type?: string;
  address_doc_upload?: string;
  ownership_doc_upload?: string;
  company_name?: string;
  company_reg_number?: string;
  company_reg_address?: string;
  certificate_of_incorporation?: string;
  director_name?: string;
  bank_statements_upload?: string;
  source_of_funds?: string;
  purchase_explanation?: string;
};

const SOURCES = [
  "Salary / employment",
  "Savings",
  "Inheritance",
  "Sale of property",
  "high value property",
  "oversea company",
  "complex ownership structure",
];

export default function LandlordVerification() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const { register, handleSubmit, watch, setValue, formState: { isSubmitting } } = useForm<Form>();
  const [done, setDone] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [tokenInfo, setTokenInfo] = useState<any>(null);
  const [tokenError, setTokenError] = useState<string | null>(null);

  // Local upload state — mirrors the LandlordAdmin pattern. Each PublicUpload
  // posts the file and bubbles back the absolute URL we then drop into the
  // form payload at submit time.
  const [uploads, setUploads] = useState<Partial<Record<
    "id_document_upload" | "visa_snapshot" | "address_doc_upload"
    | "ownership_doc_upload" | "certificate_of_incorporation" | "bank_statements_upload",
    string
  >>>({});

  function setUpload<K extends keyof typeof uploads>(key: K, url: string | undefined) {
    setUploads((cur) => ({ ...cur, [key]: url }));
    setValue(key as any, url ?? "");
  }

  useEffect(() => {
    if (!token) { setTokenError("Missing token in URL."); return; }
    publicApi.get(`/auth/form-token?token=${encodeURIComponent(token)}&form=landlord_verification`)
      .then((r) => setTokenInfo(r.data))
      .catch((e) => setTokenError(e?.response?.data?.detail ?? "Invalid or expired link"));
  }, [token]);

  const isCompany = watch("individual_or_company") === "Company";
  const residency = watch("residency");

  async function onSubmit(values: Form) {
    setServerError(null);
    // Strip empties + merge in uploads so an empty optional URL doesn't 422.
    const payload: Record<string, any> = {};
    for (const [k, v] of Object.entries(values)) {
      if (v === "" || v === undefined || v === null) continue;
      payload[k] = v;
    }
    Object.assign(payload, uploads);
    try {
      await publicApi.post(
        `/api/forms/landlord-verification?token=${encodeURIComponent(token!)}`,
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
        <div className="kicker">Verification submitted</div>
        <h2 className="mt-1">Thank you</h2>
        <p className="text-ink-soft mt-3">We'll review your documents and be in touch.</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      <header className="rounded-lg border border-cream-300 bg-white shadow-paper p-6 md:p-8"
        style={{ backgroundImage: "radial-gradient(600px 250px at 100% 0%, rgba(201, 162, 76, 0.07), transparent 60%)" }}>
        <div className="kicker">Stage 2 · Identity verification</div>
        <h1 className="mt-1">Identity verification</h1>
        <p className="mt-3 text-ink-soft max-w-2xl">
          We're required to verify your identity under the Money Laundering Regulations 2017.
        </p>
      </header>

      <Section title="About you">
        <Field label="Individual or company" required>
          <select className="input" {...register("individual_or_company", { required: true })}>
            <option value="">—</option>
            <option>Individual</option>
            <option>Company</option>
          </select>
        </Field>
        <Field label="Residency status" required>
          <select className="input" {...register("residency", { required: true })}>
            <option value="">—</option>
            <option>UK Resident</option>
            <option>Non-resident (overseas)</option>
          </select>
        </Field>
      </Section>

      <Section title="Identity">
        <Field label="ID document type">
          <select className="input" {...register("id_document_type")}>
            <option value="">—</option>
            <option>Passport</option>
            <option>National ID card</option>
          </select>
        </Field>
        <PublicUpload
          token={token!} propertyId={tokenInfo.property_id}
          bucket="id_document"
          label="ID document"
          hint="Photo of your passport or national ID card."
          accept="application/pdf,image/*"
          value={uploads.id_document_upload}
          onChange={(u) => setUpload("id_document_upload", u)}
        />
        {residency?.toLowerCase().includes("non") && (
          <PublicUpload
            token={token!} propertyId={tokenInfo.property_id}
            bucket="visa_snapshot"
            label="Visa / BRP snapshot"
            hint="Required for non-UK residents."
            accept="application/pdf,image/*"
            value={uploads.visa_snapshot}
            onChange={(u) => setUpload("visa_snapshot", u)}
          />
        )}
      </Section>

      <Section title="Proof of address">
        <Field label="Document type">
          <select className="input" {...register("address_doc_type")}>
            <option value="">—</option>
            <option>Utility bill</option>
            <option>Bank statement</option>
            <option>Tax statement</option>
          </select>
        </Field>
        <PublicUpload
          token={token!} propertyId={tokenInfo.property_id}
          bucket="address_doc"
          label="Proof of address"
          hint="Dated within the last 3 months. Mobile bills aren't accepted."
          accept="application/pdf,image/*"
          value={uploads.address_doc_upload}
          onChange={(u) => setUpload("address_doc_upload", u)}
        />
      </Section>

      <Section title="Proof of ownership">
        <PublicUpload
          token={token!} propertyId={tokenInfo.property_id}
          bucket="ownership_doc"
          label="Ownership document"
          hint="Title register, mortgage statement, or recent SDLT receipt."
          accept="application/pdf,image/*"
          value={uploads.ownership_doc_upload}
          onChange={(u) => setUpload("ownership_doc_upload", u)}
        />
      </Section>

      {isCompany && (
        <Section title="Company details">
          <Field label="Company name"><input className="input" {...register("company_name")} /></Field>
          <Field label="Company reg number"><input className="input" {...register("company_reg_number")} /></Field>
          <Field label="Company reg address"><input className="input" {...register("company_reg_address")} /></Field>
          <Field label="Director name"><input className="input" {...register("director_name")} /></Field>
          <PublicUpload
            token={token!} propertyId={tokenInfo.property_id}
            bucket="incorporation_doc"
            label="Certificate of incorporation"
            accept="application/pdf,image/*"
            value={uploads.certificate_of_incorporation}
            onChange={(u) => setUpload("certificate_of_incorporation", u)}
          />
          <PublicUpload
            token={token!} propertyId={tokenInfo.property_id}
            bucket="bank_statements"
            label="Bank statements"
            hint="Most recent 3 months."
            accept="application/pdf,image/*"
            value={uploads.bank_statements_upload}
            onChange={(u) => setUpload("bank_statements_upload", u)}
          />
        </Section>
      )}

      <Section title="Source of funds">
        <Field label="Source of funds">
          <select className="input" {...register("source_of_funds")}>
            <option value="">—</option>
            {SOURCES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="Purchase / acquisition explanation">
          <input className="input" {...register("purchase_explanation")} />
        </Field>
      </Section>

      {serverError && <div className="card p-4 bg-rose-50 text-rose-700 border-rose-200">{serverError}</div>}

      <div className="flex justify-end">
        <button type="submit" className="btn-primary" disabled={isSubmitting}>
          {isSubmitting ? "Submitting…" : "Submit verification"}
        </button>
      </div>
    </form>
  );
}
