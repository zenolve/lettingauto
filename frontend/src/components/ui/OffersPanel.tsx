import { useCallback, useEffect, useState } from "react";

import { api } from "../../lib/api";
import { useConfirm } from "./ConfirmDialog";

type Offer = {
  id: string;
  name?: string;
  status: string;
  tenant_ids: string[];
  offered_rent?: number;
  rent_frequency?: string;
  deposit?: number;
  holding_deposit?: number;
  start_date?: string;
  end_date?: string;
  tenancy_term?: string;
  holding_deposit_deadline?: string;
  created_at?: string;
  closed_at?: string;
  close_reason?: string;
  created_by?: string;
};

const TERMINAL = new Set([
  "Rejected_By_Landlord", "Withdrawn_By_Tenant", "Expired", "Failed_Referencing", "Superseded",
]);

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    Pending: "bg-amber-50 text-amber-800 ring-amber-200",
    Accepted: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  };
  const cls = map[status] ?? "bg-slate-100 text-slate-600 ring-slate-200";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ring-1 ${cls}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function money(n?: number): string {
  if (n == null) return "—";
  return `£${n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}

/**
 * Stage-4 competing-offers panel (Gap 5). Lists every Offer row on the
 * property with its commercial terms and lifecycle status, and lets the agent
 * accept / reject / withdraw a Pending offer. Accepting links the tenants to
 * the property and supersedes the rivals (handled server-side).
 */
export function OffersPanel({ propertyId, onChanged }: { propertyId: string; onChanged?: () => void }) {
  const confirm = useConfirm();
  const [offers, setOffers] = useState<Offer[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api.get<{ offers: Offer[] }>(`/api/properties/${propertyId}/offers`)
      .then((r) => setOffers(r.data.offers))
      .catch((e) => setErr(e?.response?.data?.detail ?? "Failed to load offers"));
  }, [propertyId]);

  useEffect(() => { load(); }, [load]);

  async function act(offer: Offer, action: "accept" | "reject" | "withdraw") {
    if (action !== "accept") {
      const ok = await confirm({
        title: action === "reject" ? "Mark offer as rejected by landlord?" : "Withdraw this offer?",
        body: action === "reject"
          ? "Records the landlord declining this offer. If it was the accepted offer, the tenant link is rolled back."
          : "Records the tenant pulling out. The DocuSign envelope is voided and, if this was the accepted offer, the tenant link is rolled back.",
        confirmLabel: action === "reject" ? "Mark rejected" : "Withdraw offer",
        tone: "warning",
      });
      if (!ok) return;
    }
    let reason: string | null = null;
    if (action !== "accept") {
      reason = window.prompt(`Optional reason (${action}):`, "") ?? null;
    }

    setBusy(offer.id); setErr(null);
    try {
      await api.post(`/api/offers/${offer.id}/${action}`, reason ? { reason } : {});
      load();
      onChanged?.();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? `${action} failed`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="card p-5 md:col-span-2">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-serif text-base font-semibold text-navy-700">Offers</h3>
        <span className="text-xs text-ink-muted">
          {offers ? `${offers.length} total · ${offers.filter((o) => o.status === "Pending").length} pending` : ""}
        </span>
      </div>

      {err && <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded px-2.5 py-1.5 mb-3">{err}</div>}

      {!offers ? (
        <p className="text-sm text-ink-muted">Loading…</p>
      ) : offers.length === 0 ? (
        <p className="text-sm text-ink-muted">No offers recorded yet. Use “Record offer” to add one.</p>
      ) : (
        <ul className="divide-y divide-cream-200">
          {offers.map((o) => {
            const isBusy = busy === o.id;
            const terminal = TERMINAL.has(o.status);
            return (
              <li key={o.id} className="py-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-ink truncate">{o.name ?? o.id}</span>
                    <StatusBadge status={o.status} />
                  </div>
                  <div className="text-xs text-ink-muted mt-0.5">
                    {money(o.offered_rent)}{o.rent_frequency ? ` / ${o.rent_frequency === "Weekly" ? "wk" : "mo"}` : ""}
                    {" · deposit "}{money(o.deposit)}
                    {o.start_date ? ` · from ${o.start_date}` : ""}
                    {o.tenancy_term ? ` · ${o.tenancy_term}` : ""}
                  </div>
                  {terminal && o.close_reason && (
                    <div className="text-xs text-ink-muted mt-0.5 italic">{o.close_reason}</div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {o.status === "Pending" && (
                    <button type="button" disabled={isBusy}
                      className="text-xs px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-50"
                      onClick={() => act(o, "accept")}>
                      {isBusy ? "…" : "Accept"}
                    </button>
                  )}
                  {(o.status === "Pending" || o.status === "Accepted") && (
                    <>
                      <button type="button" disabled={isBusy}
                        className="text-xs px-3 py-1.5 rounded border border-amber-300 text-amber-800 hover:bg-amber-50 disabled:opacity-50"
                        onClick={() => act(o, "reject")}>
                        Reject
                      </button>
                      <button type="button" disabled={isBusy}
                        className="text-xs px-3 py-1.5 rounded border border-rose-300 text-rose-800 hover:bg-rose-50 disabled:opacity-50"
                        onClick={() => act(o, "withdraw")}>
                        Withdraw
                      </button>
                    </>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
