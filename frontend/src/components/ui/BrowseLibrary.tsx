import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../../lib/api";
import { STAGES } from "../../lib/stages";

type LibraryDoc = {
  id: string;
  name: string;
  stage: number;
  default_mode: "sign" | "email_pdf" | "email_html";
  source: "library_file" | "master_doc";
  signers: string[];
  description: string;
  has_real_content: boolean;
  tenancy_types?: string[] | null;
};

type QueueEntry = {
  doc_id: string;
  stage: number;
  name: string;
  default_mode: "sign" | "email_pdf" | "email_html" | null;
  has_real_content: boolean;
};

type Props = {
  propertyId: string;
  /** The stage the agent is currently on — used for the modal "current stage first"
   * grouping and as the default stage for newly added queue items. */
  stage: number;
  buttonLabel?: string;
};

const MODE_BADGE: Record<NonNullable<LibraryDoc["default_mode"]>, { label: string; cls: string }> = {
  sign:       { label: "Sign",      cls: "bg-violet-50 text-violet-700 border-violet-200" },
  email_pdf:  { label: "Email PDF", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  email_html: { label: "Email",     cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
};

/**
 * Two-part widget:
 *   1. "Browse document library" button that opens a modal of every TPL +
 *      library file. Each row has an [Add] button — clicking it queues the
 *      doc for this property+stage (persisted server-side). After adding,
 *      the row shows "Added" and the modal stays open so the agent can
 *      queue several at once.
 *   2. Inline queue card below the button — lists added docs for this stage,
 *      each with [Open editor] and [Delete] actions. The Open button drops
 *      the agent into the per-property editor where they pick the send mode
 *      (Sign / Email PDF / Send as email).
 *
 * The list of docs in the modal is filtered by the property's tenancy type
 * (so the APT TA doesn't show on a Common Law property and vice versa).
 */
export function BrowseLibrary({ propertyId, stage, buttonLabel = "Browse document library" }: Props) {
  const [open, setOpen] = useState(false);
  const [docs, setDocs] = useState<LibraryDoc[] | null>(null);
  const [tenancyType, setTenancyType] = useState<string | null>(null);
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState<string | null>(null);
  const nav = useNavigate();

  // ---- Queue (always loaded — needed for the inline card) ---------------
  const refreshQueue = useCallback(async () => {
    try {
      const r = await api.get<{ queue: QueueEntry[] }>(
        `/api/library/property/${propertyId}/queue?stage=${stage}`,
      );
      setQueue(r.data.queue);
    } catch (e: any) {
      // Non-fatal — the queue is a nicety, not a hard requirement.
      console.warn("library queue load failed", e);
    }
  }, [propertyId, stage]);

  useEffect(() => { refreshQueue(); }, [refreshQueue]);

  // ---- Lazy-load the catalog when the modal opens ----------------------
  useEffect(() => {
    if (!open || docs) return;
    api.get<{ documents: LibraryDoc[]; tenancy_type?: string | null }>(
      `/api/library?property_id=${propertyId}`,
    )
      .then((r) => { setDocs(r.data.documents); setTenancyType(r.data.tenancy_type ?? null); })
      .catch((e) => setErr(e?.response?.data?.detail ?? "Failed to load library"));
  }, [open, docs, propertyId]);

  const queuedIds = useMemo(() => new Set(queue.map((q) => q.doc_id)), [queue]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!docs) return null;
    if (!needle) return docs;
    return docs.filter((d) =>
      [d.name, d.id, d.description].filter(Boolean).some((v) => v.toLowerCase().includes(needle)),
    );
  }, [docs, q]);

  const grouped = useMemo(() => {
    if (!filtered) return null;
    const map = new Map<number, LibraryDoc[]>();
    for (const d of filtered) (map.get(d.stage) ?? map.set(d.stage, []).get(d.stage)!).push(d);
    return map;
  }, [filtered]);

  const stagesInOrder = useMemo(() => {
    if (!grouped) return [];
    const all = Array.from(grouped.keys());
    const current = all.filter((s) => s === stage);
    const rest = all.filter((s) => s !== stage).sort((a, b) => a - b);
    return [...current, ...rest];
  }, [grouped, stage]);

  async function addToQueue(doc: LibraryDoc) {
    setAdding(doc.id);
    try {
      await api.post(`/api/library/property/${propertyId}/queue`, {
        doc_id: doc.id,
        stage,  // queue all adds at the *current* stage, even if the doc's home stage differs
      });
      await refreshQueue();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Add failed");
    } finally { setAdding(null); }
  }

  async function removeFromQueue(doc_id: string) {
    try {
      await api.delete(`/api/library/property/${propertyId}/queue/${doc_id}?stage=${stage}`);
      await refreshQueue();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Delete failed");
    }
  }

  function stageName(order: number): string {
    return STAGES.find((s) => s.order === order)?.name ?? `Stage ${order}`;
  }

  function modeBadge(mode: LibraryDoc["default_mode"]) {
    const b = MODE_BADGE[mode];
    return <span className={`text-[10px] px-2 py-0.5 rounded border ${b.cls}`}>{b.label}</span>;
  }

  return (
    <div className="space-y-3">
      <button className="btn-secondary text-sm" onClick={() => setOpen(true)}>
        {buttonLabel} →
      </button>

      {/* Queue card — appears under the Browse button once the agent has added
          at least one document. */}
      {queue.length > 0 && (
        <section className="card p-4 bg-cream-100">
          <div className="flex items-baseline justify-between mb-2">
            <h3 className="text-sm font-semibold text-ink">Added to this stage</h3>
            <span className="text-xs text-ink-muted">{queue.length} doc{queue.length === 1 ? "" : "s"}</span>
          </div>
          <ul className="divide-y divide-cream-300">
            {queue.map((q) => (
              <li key={q.doc_id} className="py-2 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-ink truncate">{q.name}</div>
                  <div className="text-xs text-ink-muted">
                    Stage {q.stage}
                    {q.default_mode && <> · default {MODE_BADGE[q.default_mode].label.toLowerCase()}</>}
                    {!q.has_real_content && <> · placeholder</>}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Link
                    to={`/agent/properties/${propertyId}/library/${q.doc_id}`}
                    className="btn-ghost text-navy-700 text-xs">
                    Open editor →
                  </Link>
                  <button
                    onClick={() => removeFromQueue(q.doc_id)}
                    className="text-xs text-rose-600 hover:text-rose-800"
                    title="Remove from queue">
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {open && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 flex items-center justify-center p-4"
             onClick={() => setOpen(false)}>
          <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[85vh] flex flex-col"
               onClick={(e) => e.stopPropagation()}>
            <header className="flex items-baseline justify-between px-5 py-4 border-b border-cream-300">
              <div>
                <h2 className="text-lg font-semibold text-navy-700">Document library</h2>
                <p className="text-xs text-ink-muted">
                  Current stage <strong>{stage}</strong> ({stageName(stage)}) shown first.
                  {tenancyType && <> Filtered to docs valid for <strong>{tenancyType}</strong> tenancies.</>}
                </p>
              </div>
              <button className="text-ink-muted hover:text-ink" onClick={() => setOpen(false)} aria-label="Close">✕</button>
            </header>

            <div className="px-5 pt-3">
              <input className="input w-full" placeholder="Search by name, id, description…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>

            <div className="overflow-y-auto p-5 space-y-5">
              {err && <p className="text-sm text-rose-600">{err}</p>}
              {!docs && !err && <p className="text-sm text-ink-muted">Loading…</p>}
              {grouped && grouped.size === 0 && (
                <p className="text-sm text-ink-muted">No documents match.</p>
              )}
              {grouped && stagesInOrder.map((stageOrder) => {
                const isCurrent = stageOrder === stage;
                const rows = grouped.get(stageOrder) ?? [];
                if (rows.length === 0) return null;
                return (
                  <section key={stageOrder} className="space-y-2">
                    <h3 className={`text-xs uppercase tracking-kicker ${isCurrent ? "text-navy-700 font-semibold" : "text-ink-muted"}`}>
                      {isCurrent ? `Recommended for ${stageName(stageOrder)} (current stage)` : `Stage ${stageOrder} · ${stageName(stageOrder)}`}
                    </h3>
                    {rows.map((d) => {
                      const isQueued = queuedIds.has(d.id);
                      return (
                        <div key={d.id} className="p-3 rounded-md border border-cream-300 hover:border-navy-300 transition-colors flex items-start gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-ink truncate">{d.name}</div>
                            <div className="text-xs text-ink-muted mt-0.5">{d.description}</div>
                            <div className="flex flex-wrap items-center gap-2 mt-1.5">
                              {modeBadge(d.default_mode)}
                              {!d.has_real_content && (
                                <span className="text-[10px] px-2 py-0.5 rounded bg-cream-200 text-ink-muted border border-cream-400">Placeholder</span>
                              )}
                              {d.signers.length > 0 && (
                                <span className="text-[10px] text-ink-muted">Signers: {d.signers.join(", ")}</span>
                              )}
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-2 shrink-0">
                            {isQueued ? (
                              <span className="text-[11px] px-2 py-1 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">✓ Added</span>
                            ) : (
                              <button
                                onClick={() => addToQueue(d)}
                                disabled={adding === d.id}
                                className="text-xs px-3 py-1 rounded bg-navy-600 text-white hover:bg-navy-700 disabled:opacity-50">
                                {adding === d.id ? "Adding…" : "+ Add"}
                              </button>
                            )}
                            <button
                              onClick={() => nav(`/agent/properties/${propertyId}/library/${d.id}`)}
                              className="text-xs text-navy-700 hover:underline">
                              Open editor →
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </section>
                );
              })}
            </div>

            <footer className="px-5 py-3 border-t border-cream-300 flex items-center justify-between text-xs text-ink-muted">
              <span>{queue.length} doc{queue.length === 1 ? "" : "s"} queued for this stage</span>
              <button className="btn-secondary text-xs" onClick={() => setOpen(false)}>Done</button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
