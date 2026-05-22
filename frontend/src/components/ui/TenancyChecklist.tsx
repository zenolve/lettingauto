import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../../lib/api";

type CatalogItem = {
  id: string;
  name: string;
  priority: "Critical" | "High" | "Medium" | "Low" | null;
  applies_to: string[];
  is_template: boolean;
  is_gate_item: boolean;
  status: string | null;
};

type Catalog = {
  items: CatalogItem[];
  fetched_at: number;  // epoch ms — only kept locally for the refresh hint
};

const CACHE_KEY = "tenancy_checklist_catalog_v1";

function readCache(): Catalog | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Catalog;
    if (!Array.isArray(parsed.items)) return null;
    return parsed;
  } catch { return null; }
}

function writeCache(c: Catalog): void {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify(c)); } catch { /* private mode etc. */ }
}

const PRIORITY_TONE: Record<NonNullable<CatalogItem["priority"]>, string> = {
  Critical: "bg-rose-50 text-rose-700 border-rose-200",
  High:     "bg-amber-50 text-amber-700 border-amber-200",
  Medium:   "bg-cream-200 text-ink-soft border-cream-400",
  Low:      "bg-cream-100 text-ink-muted border-cream-300",
};

/**
 * Collapsible tenancy-checklist panel for Stage 7 (Pre Move-in).
 *
 * Loads the catalog of checklist items from Airtable once and caches in
 * localStorage — the catalog rarely changes and a stale list is fine. The
 * refresh button forces a fresh pull when Farnaz updates the table directly.
 *
 * Ticking a row links that catalog item into ``Properties.Tenancy Checklist``;
 * unticking unlinks it. Initial load shows nothing ticked (no auto-population
 * today — see the agent brief on 2026-05-16).
 */
export function TenancyChecklist({ propertyId }: { propertyId: string }) {
  const [open, setOpen] = useState(false);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // --- Catalog load (cache-first) -----------------------------------------
  const loadCatalog = useCallback(async (force: boolean) => {
    if (!force) {
      const cached = readCache();
      if (cached) { setCatalog(cached); return; }
    }
    setLoading(true); setErr(null);
    try {
      const r = await api.get<{ items: CatalogItem[] }>("/api/checklist/catalog");
      const next: Catalog = { items: r.data.items, fetched_at: Date.now() };
      writeCache(next);
      setCatalog(next);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Failed to load checklist");
    } finally {
      setLoading(false);
    }
  }, []);

  // --- Per-property tick state -------------------------------------------
  const refreshTicked = useCallback(async () => {
    try {
      const r = await api.get<{ ticked: string[] }>(`/api/properties/${propertyId}/checklist`);
      setTicked(new Set(r.data.ticked));
    } catch (e: any) {
      // Non-fatal — checklist is additive UX; let the catalog still render.
      console.warn("checklist ticked-state fetch failed", e);
    }
  }, [propertyId]);

  useEffect(() => {
    // Catalog: load lazily the first time the panel opens (don't pay the
    // round-trip on stages 1-6 where the panel isn't shown).
    if (open && !catalog) loadCatalog(false);
    if (open) refreshTicked();
  }, [open, catalog, loadCatalog, refreshTicked]);

  async function toggle(item: CatalogItem) {
    setBusyId(item.id); setErr(null);
    const willTick = !ticked.has(item.id);
    try {
      if (willTick) {
        await api.post(`/api/properties/${propertyId}/checklist/${item.id}`);
      } else {
        await api.delete(`/api/properties/${propertyId}/checklist/${item.id}`);
      }
      // Optimistic re-fetch so the rollup count is right.
      await refreshTicked();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Update failed");
    } finally {
      setBusyId(null);
    }
  }

  const stats = useMemo(() => {
    const total = catalog?.items.length ?? 0;
    const done = catalog ? catalog.items.filter((it) => ticked.has(it.id)).length : ticked.size;
    return { total, done };
  }, [catalog, ticked]);

  return (
    <section className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-cream-100 transition-colors text-left">
        <div>
          <h3 className="!text-base !text-navy-700 !font-serif">Tenancy checklist</h3>
          <p className="text-xs text-ink-muted mt-0.5">
            Confirm every step before keys are released. Items are pulled from the master Tenancy Checklist table.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-ink-muted">
            {stats.done} / {stats.total || "—"} ticked
          </span>
          <span className="text-ink-muted text-lg leading-none">{open ? "−" : "+"}</span>
        </div>
      </button>

      {open && (
        <div className="border-t border-cream-300">
          {/* Toolbar — refresh + last-pulled hint */}
          <div className="flex items-center justify-between px-5 py-3 bg-cream-50 border-b border-cream-300">
            <div className="text-xs text-ink-muted">
              {catalog?.fetched_at
                ? <>Catalog cached locally — last refreshed {new Date(catalog.fetched_at).toLocaleString()}.</>
                : <>Catalog not loaded.</>}
            </div>
            <button
              type="button"
              onClick={() => loadCatalog(true)}
              disabled={loading}
              title="Re-pull the checklist from Airtable"
              className="btn-ghost text-xs text-navy-700 disabled:opacity-50">
              {loading ? "Refreshing…" : "⟳ Refresh"}
            </button>
          </div>

          {err && <div className="m-4 p-3 rounded bg-rose-50 text-rose-700 text-sm border border-rose-200">{err}</div>}

          {/* List */}
          <ul className="divide-y divide-cream-300">
            {!catalog && !loading && (
              <li className="px-5 py-6 text-sm text-ink-muted text-center">
                Click the refresh button above to pull the checklist from Airtable.
              </li>
            )}
            {loading && !catalog && (
              <li className="px-5 py-6 text-sm text-ink-muted text-center">Loading checklist…</li>
            )}
            {catalog && catalog.items.length === 0 && (
              <li className="px-5 py-6 text-sm text-ink-muted text-center">
                The Tenancy Checklist table in Airtable is empty.
              </li>
            )}
            {catalog?.items.map((item) => {
              const isTicked = ticked.has(item.id);
              const isBusy = busyId === item.id;
              return (
                <li key={item.id} className={`px-5 py-3 flex items-start gap-3 transition-colors ${isTicked ? "bg-cream-100" : "hover:bg-cream-50"}`}>
                  <input
                    type="checkbox"
                    checked={isTicked}
                    disabled={isBusy}
                    onChange={() => toggle(item)}
                    className="mt-0.5 h-4 w-4 cursor-pointer accent-navy-700"
                    aria-label={`Tick: ${item.name}`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className={`text-sm ${isTicked ? "text-ink-muted line-through" : "text-ink"}`}>
                      {item.name}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 mt-1">
                      {item.priority && (
                        <span className={`text-[10px] px-2 py-0.5 rounded border ${PRIORITY_TONE[item.priority]}`}>
                          {item.priority}
                        </span>
                      )}
                      {item.is_gate_item && (
                        <span className="text-[10px] px-2 py-0.5 rounded border bg-navy-50 text-navy-700 border-navy-200">
                          Gate item
                        </span>
                      )}
                      {item.applies_to.slice(0, 3).map((a) => (
                        <span key={a} className="text-[10px] px-2 py-0.5 rounded border bg-cream-100 text-ink-muted border-cream-300">
                          {a}
                        </span>
                      ))}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
