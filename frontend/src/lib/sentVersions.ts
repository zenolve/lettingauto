/**
 * Sent-document versions (backend: services/sent_documents.py, migration 004).
 *
 * A send can revise an earlier send of the same document: it carries
 * `revises_id`, a version number, and the replaced send gets `superseded_at`.
 * The API returns flat rows; these helpers turn them into one chain per
 * document - the current version plus the ones it replaced.
 */

type Versioned = { submission_id: string; revises_id?: string | null };

/** Group sent rows into version chains, keeping the input order of the
 * current versions (the API sends rows newest first). */
export function groupVersions<T extends Versioned>(rows: T[]): { current: T; earlier: T[] }[] {
  const byId = new Map(rows.map((r) => [r.submission_id, r]));
  const replaced = new Set(rows.map((r) => r.revises_id).filter((id): id is string => !!id));
  return rows
    .filter((r) => !replaced.has(r.submission_id))
    .map((current) => {
      const earlier: T[] = [];
      const seen = new Set([current.submission_id]);
      let prev = current.revises_id ? byId.get(current.revises_id) : undefined;
      while (prev && !seen.has(prev.submission_id)) {
        earlier.push(prev);
        seen.add(prev.submission_id);
        prev = prev.revises_id ? byId.get(prev.revises_id) : undefined;
      }
      return { current, earlier };
    });
}

/** "11 Oct, 14:20" - the time matters once a document is revised the same day. */
export function sentWhen(v: { sent_at?: string | null; submitted_date?: string | null }): string {
  const iso = v.sent_at ?? v.submitted_date;
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // A date-only value (pre-versioning rows) has no meaningful time to show.
  if (!v.sent_at) return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
