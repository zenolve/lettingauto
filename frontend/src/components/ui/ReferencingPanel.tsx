import { useEffect, useState } from "react";

import { api } from "../../lib/api";

type Tenant = {
  id: string;
  name?: string;
  email?: string;
  paragon_reference?: string;
  outcome: "Pass" | "Conditional" | "Fail" | "Pending";
  referencing_recorded: boolean;
  is_student: boolean;
  has_guarantor: boolean;
};

type State = {
  property_id: string;
  tenants: Tenant[];
  landlord_approval_received: boolean;
  referencing_recorded: boolean;
  monthly_rent?: number;
  guarantor_name?: string;
};

const OUTCOMES: Array<Tenant["outcome"]> = ["Pending", "Pass", "Conditional", "Fail"];

const OUTCOME_CLS: Record<Tenant["outcome"], string> = {
  Pass:        "bg-emerald-50 text-emerald-700 border-emerald-200",
  Conditional: "bg-amber-50 text-amber-700 border-amber-200",
  Fail:        "bg-rose-50 text-rose-700 border-rose-200",
  Pending:     "bg-slate-50 text-slate-500 border-slate-200",
};

/**
 * Stage 5 referencing widget. Lets the agent:
 *   1. Instruct Paragon for any tenant who doesn't yet have a reference number.
 *   2. Record the per-tenant outcome (Pass / Conditional / Fail).
 *   3. Tick the landlord-approval-received flag.
 * All writes go through /api/properties/{id}/referencing/* — no Airtable
 * manual entry needed.
 */
export function ReferencingPanel({ propertyId, disabled = false }: { propertyId: string; disabled?: boolean }) {
  const [state, setState] = useState<State | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // tenant id being mutated, or "instruct"
  const [note, setNote] = useState<string | null>(null);

  async function refresh() {
    try {
      const r = await api.get<State>(`/api/properties/${propertyId}/referencing`);
      setState(r.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Failed to load referencing");
    }
  }

  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [propertyId]);

  async function instruct() {
    setBusy("instruct"); setNote(null);
    try {
      const r = await api.post(`/api/properties/${propertyId}/referencing/instruct`);
      const refs = (r.data?.instructed ?? []).filter((x: any) => x.reference);
      setNote(refs.length === 0 ? "Every tenant already has a Paragon reference." : `Instructed ${refs.length} tenant(s).`);
      await refresh();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Instruct failed");
    } finally { setBusy(null); }
  }

  async function patchOutcome(tenantId: string, outcome: Tenant["outcome"]) {
    setBusy(tenantId); setNote(null);
    try {
      const r = await api.post(`/api/properties/${propertyId}/referencing/outcome`, { tenant_id: tenantId, outcome });
      if (r.data?.warnings?.length) setNote(`⚠ ${r.data.warnings.join(" ")}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Outcome update failed");
    } finally { setBusy(null); }
  }

  async function toggleLLApproval(v: boolean) {
    setBusy("ll"); setNote(null);
    try {
      const r = await api.post(`/api/properties/${propertyId}/referencing/outcome`, {
        landlord_approval_received: v,
      });
      if (r.data?.warnings?.length) setNote(`⚠ ${r.data.warnings.join(" ")}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Approval toggle failed");
    } finally { setBusy(null); }
  }

  if (err) return <section className="card p-4 text-rose-700 bg-rose-50">{err}</section>;
  if (!state) return <section className="card p-4"><span className="text-sm text-slate-500">Loading referencing…</span></section>;

  if (state.tenants.length === 0) {
    return (
      <section className="card p-4">
        <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-2">Paragon referencing</h3>
        <p className="text-sm text-slate-500">No tenants on this property yet. Record an offer at stage 4 first.</p>
      </section>
    );
  }

  const anyMissing = state.tenants.some((t) => !t.paragon_reference);

  return (
    <section className="card p-4 col-span-1 md:col-span-2">
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm uppercase tracking-wide text-slate-500">Paragon referencing</h3>
        <button
          className="btn-secondary text-sm"
          onClick={instruct}
          disabled={disabled || busy === "instruct" || !anyMissing}
          title={disabled ? "Locked until property reaches stage 5 (Referencing)" : undefined}>
          {busy === "instruct" ? "Instructing…" : anyMissing ? "Instruct Paragon" : "All instructed"}
        </button>
      </div>
      {disabled && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2 mb-2">
          Locked — property hasn't reached Stage 5 yet. Record an offer first.
        </p>
      )}

      {note && (
        <p className={`text-xs mb-2 ${note.startsWith("⚠") ? "text-amber-700" : "text-emerald-700"}`}>
          {note}
        </p>
      )}

      <table className="w-full text-sm">
        <thead className="text-slate-500 text-xs uppercase tracking-wide">
          <tr className="text-left">
            <th className="py-2">Tenant</th>
            <th>Paragon ref</th>
            <th>Outcome</th>
            <th>Flags</th>
            <th></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {state.tenants.map((t) => (
            <tr key={t.id}>
              <td className="py-2 align-top">
                <div className="font-medium text-slate-800">{t.name ?? "—"}</div>
                <div className="text-xs text-slate-500">{t.email}</div>
              </td>
              <td className="align-top">
                {t.paragon_reference ? <code className="text-xs">{t.paragon_reference}</code> : <span className="text-xs text-slate-400">—</span>}
              </td>
              <td className="align-top">
                <span className={`inline-block text-xs px-2 py-0.5 rounded border ${OUTCOME_CLS[t.outcome]}`}>
                  {t.outcome}
                </span>
              </td>
              <td className="align-top text-xs text-slate-500">
                {t.is_student && <div>Student</div>}
                {t.has_guarantor && <div>Guarantor</div>}
              </td>
              <td className="align-top text-right">
                <div className="flex flex-wrap gap-1 justify-end">
                  {OUTCOMES.filter((o) => o !== t.outcome).map((o) => (
                    <button key={o} onClick={() => patchOutcome(t.id, o)} disabled={busy === t.id}
                      className={`text-xs px-2 py-0.5 rounded border hover:bg-slate-50 ${OUTCOME_CLS[o]}`}>
                      → {o}
                    </button>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-ink-soft">
          <input
            type="checkbox"
            checked={state.landlord_approval_received}
            disabled={busy === "ll"}
            onChange={(e) => toggleLLApproval(e.target.checked)}
          />
          Landlord has accepted the offer
          <span className="text-xs text-ink-muted">(Property.LL_Offer_Accepted)</span>
        </label>
        <span className={`text-xs px-2 py-0.5 rounded border ${state.referencing_recorded && state.landlord_approval_received ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-slate-50 text-slate-500 border-slate-200"}`}>
          {state.referencing_recorded && state.landlord_approval_received
            ? "Stage 6 unlocked"
            : state.referencing_recorded
              ? "Awaiting landlord acceptance"
              : "Awaiting outcomes"}
        </span>
      </div>
    </section>
  );
}
