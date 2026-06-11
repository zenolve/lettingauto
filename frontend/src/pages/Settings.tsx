import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { useAgency } from "../lib/agency";

/** Agency settings: profile, document branding, billing. */
export default function Settings() {
  const agency = useAgency((s) => s.agency);
  const load = useAgency((s) => s.load);

  const [form, setForm] = useState({
    name: "", email: "", phone: "", office_address: "", website: "",
    brand_navy: "#004AAD", brand_gold: "#C9A24C",
  });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (agency) {
      setForm({
        name: agency.name ?? "",
        email: agency.email ?? "",
        phone: agency.phone ?? "",
        office_address: agency.office_address ?? "",
        website: agency.website ?? "",
        brand_navy: agency.brand_navy ?? "#004AAD",
        brand_gold: agency.brand_gold ?? "#C9A24C",
      });
    }
  }, [agency]);

  if (!agency) return null;
  const billing = agency.billing;
  const canEdit = ["owner", "admin"].includes(agency.membership.role);

  function set<K extends keyof typeof form>(k: K, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function save() {
    setSaving(true);
    setMsg(null);
    setErr(null);
    try {
      await api.patch("/api/agencies/me", form);
      await load(true);
      setMsg("Saved.");
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setErr(typeof detail === "string" ? detail : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-8">
      <header>
        <div className="kicker">Settings</div>
        <h1 className="font-serif text-3xl text-navy-700 mt-1">{agency.name}</h1>
        <p className="text-sm text-ink-muted mt-1">
          Signed in as {agency.membership.email} · role: {agency.membership.role}
        </p>
      </header>

      {/* ---- Profile ---- */}
      <section className="card p-6 space-y-4">
        <h2 className="font-serif text-xl text-navy-700">Agency profile</h2>
        <p className="text-sm text-ink-muted -mt-2">
          These details appear on contracts, prescribed documents and every email sent to
          your landlords and tenants.
        </p>
        <div className="grid grid-cols-2 gap-4">
          <label className="block col-span-2">
            <span className="label mb-1.5">Agency name</span>
            <input className="input" value={form.name} disabled={!canEdit}
              onChange={(e) => set("name", e.target.value)} />
          </label>
          <label className="block">
            <span className="label mb-1.5">Contact email</span>
            <input className="input" value={form.email} disabled={!canEdit}
              onChange={(e) => set("email", e.target.value)} />
          </label>
          <label className="block">
            <span className="label mb-1.5">Phone</span>
            <input className="input" value={form.phone} disabled={!canEdit}
              onChange={(e) => set("phone", e.target.value)} />
          </label>
          <label className="block col-span-2">
            <span className="label mb-1.5">Office address</span>
            <input className="input" value={form.office_address} disabled={!canEdit}
              onChange={(e) => set("office_address", e.target.value)} />
          </label>
          <label className="block col-span-2">
            <span className="label mb-1.5">Website</span>
            <input className="input" value={form.website} disabled={!canEdit}
              onChange={(e) => set("website", e.target.value)} />
          </label>
        </div>
      </section>

      {/* ---- Branding ---- */}
      <section className="card p-6 space-y-4">
        <h2 className="font-serif text-xl text-navy-700">Document branding</h2>
        <div className="flex items-end gap-6">
          <label className="block">
            <span className="label mb-1.5">Primary colour</span>
            <input type="color" className="h-10 w-20 rounded border border-cream-300 cursor-pointer"
              value={form.brand_navy} disabled={!canEdit}
              onChange={(e) => set("brand_navy", e.target.value)} />
          </label>
          <label className="block">
            <span className="label mb-1.5">Accent colour</span>
            <input type="color" className="h-10 w-20 rounded border border-cream-300 cursor-pointer"
              value={form.brand_gold} disabled={!canEdit}
              onChange={(e) => set("brand_gold", e.target.value)} />
          </label>
          {/* live preview chip */}
          <div className="flex-1 rounded-md overflow-hidden border border-cream-300">
            <div className="px-4 py-2 text-white text-sm font-medium"
              style={{ background: form.brand_navy, borderBottom: `3px solid ${form.brand_gold}` }}>
              {form.name || "Your agency"} — Tenancy Agreement
            </div>
            <div className="px-4 py-2 text-xs text-ink-muted bg-white">Document header preview</div>
          </div>
        </div>
      </section>

      {canEdit && (
        <div className="flex items-center gap-3">
          <button className="btn-primary px-6" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
          {msg && <span className="text-sm text-emerald-700">{msg}</span>}
          {err && <span className="text-sm text-rose-700">{err}</span>}
        </div>
      )}

      {/* ---- Billing ---- */}
      <section className="card p-6 space-y-4">
        <h2 className="font-serif text-xl text-navy-700">Billing</h2>
        <p className="text-sm text-ink-muted -mt-2">
          Simple, usage-based pricing — a one-time fee per new tenancy, collected via Stripe
          when you create the tenancy. No subscription, no card kept on file.
        </p>

        <div className="grid grid-cols-3 gap-4 text-center">
          <div className="rounded-md border border-cream-300 p-4">
            <div className="text-2xl font-serif text-navy-700">£{billing.pricing.tenancy_setup_fee}</div>
            <div className="text-xs text-ink-muted mt-1">one-time per new tenancy</div>
          </div>
          <div className="rounded-md border border-cream-300 p-4">
            <div className="text-2xl font-serif text-navy-700">{billing.tenancy_fees_paid}</div>
            <div className="text-xs text-ink-muted mt-1">tenancy fees paid</div>
          </div>
          <div className="rounded-md border border-cream-300 p-4">
            <div className="text-2xl font-serif text-navy-700">{billing.tenancy_fees_pending}</div>
            <div className="text-xs text-ink-muted mt-1">awaiting payment</div>
          </div>
        </div>

        {!billing.enabled ? (
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            Billing is not configured on this server (no Stripe keys) — tenancy fees are
            skipped in this environment.
          </p>
        ) : (
          <p className="text-sm text-ink-soft">
            When you create a new tenancy you'll be sent to Stripe to pay the £{billing.pricing.tenancy_setup_fee}{" "}
            setup fee. Paid and outstanding fees are summarised above.
          </p>
        )}
      </section>
    </div>
  );
}
