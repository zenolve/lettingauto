import { useEffect, useState } from "react";

import { api } from "../../lib/api";

type Review = {
  gate_log_id: string;
  warnings: string[];
  actions: string[];
  source?: string;
  updated?: string;
  attempted_at?: string;
  result?: string;
};

/**
 * Renders the most-recent compliance/review batch attached to the property's
 * Gate_Log. Warnings render amber (must act), actions render navy (todo).
 * The agent can dismiss the entire batch — backend flips Gate Warnings
 * Dismissed on the matching Gate_Log row and the panel disappears.
 *
 * Sits ABOVE the gate-block panel because warnings are usually the cause of
 * the block; you want to see them first.
 */
export function ReviewPanel({ propertyId }: { propertyId: string }) {
  const [review, setReview] = useState<Review | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.get<{ review: Review | null }>(`/api/properties/${propertyId}/latest-review`)
      .then((r) => { if (!cancelled) setReview(r.data.review); })
      .catch(() => { if (!cancelled) setReview(null); });
    return () => { cancelled = true; };
  }, [propertyId]);

  if (review === undefined) return null; // initial load — silent
  if (!review) return null;
  if (review.warnings.length === 0 && review.actions.length === 0) return null;

  async function dismiss() {
    if (!review) return;
    if (!confirm("Dismiss this review? Future submissions will create a new one if issues remain.")) return;
    setBusy(true); setErr(null);
    try {
      await api.post(`/api/properties/${propertyId}/latest-review/${review.gate_log_id}/dismiss`);
      setReview(null);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Dismiss failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card overflow-hidden border-amber-300">
      <header className="bg-amber-50 border-b border-amber-200 px-5 py-3 flex items-start justify-between gap-3">
        <div>
          <div className="kicker text-amber-700">Review required</div>
          <h3 className="font-serif text-base font-semibold text-amber-900 mt-0.5">
            Compliance findings — {review.source ?? "latest submission"}
          </h3>
          {review.updated && (
            <p className="text-xs text-amber-800/70 mt-1">
              Updated {new Date(review.updated).toLocaleDateString()}
              {review.result && <> · gate result: <strong>{review.result}</strong></>}
            </p>
          )}
        </div>
        <button
          type="button"
          className="text-xs px-3 py-1.5 rounded border border-amber-300 bg-white text-amber-800 hover:bg-amber-100 disabled:opacity-50"
          onClick={dismiss}
          disabled={busy}>
          {busy ? "Dismissing…" : "Dismiss"}
        </button>
      </header>

      <div className="px-5 py-4 space-y-4 bg-white">
        {review.warnings.length > 0 && (
          <div>
            <div className="kicker text-rose-700 mb-1">Warnings</div>
            <ul className="space-y-1">
              {review.warnings.map((w, i) => (
                <li key={i} className="text-sm text-ink-soft flex gap-2 items-start">
                  <span aria-hidden className="text-rose-600 mt-0.5">●</span>
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {review.actions.length > 0 && (
          <div>
            <div className="kicker text-navy-700 mb-1">Actions</div>
            <ul className="space-y-1">
              {review.actions.map((a, i) => (
                <li key={i} className="text-sm text-ink-soft flex gap-2 items-start">
                  <span aria-hidden className="text-navy-600 mt-0.5">→</span>
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {err && <p className="text-xs text-rose-600">{err}</p>}
      </div>
    </section>
  );
}
