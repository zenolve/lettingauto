import { useEffect, useState } from "react";

import { api } from "../../lib/api";

type Group = {
  gate_log_id: string;
  source: string;
  to_stage?: string;
  attempted_at: string;
  updated?: string;
  dismissed: boolean;
  warnings: string[];
  actions: string[];
};

/**
 * Read-only recap of every warning/action ever raised on a property — across
 * all stages, ignoring dismissed status. Mounted under the Stage 7 Tenancy
 * Checklist so the agent sees every flagged issue in one place before
 * releasing keys.
 *
 * Stage 7 is the natural endpoint: no warnings are generated after it
 * (PG_05/06/07 don't write warnings; a post-7 PG_04 DocuSeal decline event
 * is rare). For schema-free transient surfacing, agent re-opens Stage 7 to
 * see anything new.
 *
 * Compare to ReviewPanel which shows only the most-recent non-dismissed
 * batch and is meant as an action-needed banner. This panel is the durable
 * "have you really addressed everything?" record.
 */
export function WarningsRecap({ propertyId }: { propertyId: string }) {
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.get<{ groups: Group[] }>(`/api/properties/${propertyId}/all-warnings`)
      .then((r) => { if (!cancelled) setGroups(r.data.groups); })
      .catch((e) => { if (!cancelled) setErr(e?.response?.data?.detail ?? "Failed to load warnings"); });
    return () => { cancelled = true; };
  }, [propertyId]);

  if (err) {
    return (
      <section className="card p-5 border-rose-200 bg-rose-50">
        <p className="text-sm text-rose-700">{err}</p>
      </section>
    );
  }

  if (groups === null) {
    return (
      <section className="card p-5">
        <h3 className="font-serif text-base font-semibold text-navy-700">All warnings — full history</h3>
        <p className="text-xs text-ink-muted mt-2">Loading…</p>
      </section>
    );
  }

  return (
    <section className="card overflow-hidden">
      <header className="bg-cream-50 border-b border-cream-300 px-5 py-3">
        <div className="kicker text-navy-700">Pre-move-in review</div>
        <h3 className="font-serif text-base font-semibold text-ink mt-0.5">
          All warnings — full history
        </h3>
        <p className="text-xs text-ink-soft mt-1.5">
          Every warning raised on this property across all stages, regardless of whether it was dismissed.
          <strong className="text-amber-800"> Please make sure each one has been addressed before proceeding.</strong>
        </p>
      </header>

      {groups.length === 0 ? (
        <div className="px-5 py-6 text-sm text-ink-muted text-center">
          No warnings have been raised on this property — looks clean.
        </div>
      ) : (
        <ul className="divide-y divide-cream-200">
          {groups.map((g) => (
            <li key={g.gate_log_id} className="px-5 py-4">
              <div className="flex items-baseline justify-between gap-3 mb-2">
                <div className="text-sm font-medium text-ink">
                  {g.source}
                  {g.to_stage && (
                    <span className="text-xs text-ink-muted font-normal ml-2">→ Stage {g.to_stage}</span>
                  )}
                </div>
                <div className="text-xs text-ink-muted flex items-center gap-2 shrink-0">
                  {g.dismissed && (
                    <span className="inline-block px-1.5 py-0.5 rounded bg-cream-200 text-ink-muted">
                      Dismissed
                    </span>
                  )}
                  {g.attempted_at && (
                    <span>{new Date(g.attempted_at).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "2-digit" })}</span>
                  )}
                </div>
              </div>
              {g.warnings.length > 0 && (
                <ul className="space-y-1 mb-2">
                  {g.warnings.map((w, i) => (
                    <li key={i} className="text-sm text-ink-soft flex gap-2 items-start">
                      <span aria-hidden className="text-rose-600 mt-0.5">●</span>
                      <span>{w}</span>
                    </li>
                  ))}
                </ul>
              )}
              {g.actions.length > 0 && (
                <ul className="space-y-1">
                  {g.actions.map((a, i) => (
                    <li key={i} className="text-sm text-ink-soft flex gap-2 items-start">
                      <span aria-hidden className="text-navy-600 mt-0.5">→</span>
                      <span>{a}</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
