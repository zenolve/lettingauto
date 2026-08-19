import { useEffect, useMemo, useState } from "react";

import { api } from "../../lib/api";
import { useConfirm } from "./ConfirmDialog";

type ConfirmMeta = {
  title: string;
  body: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "info" | "warning" | "danger";
};

type FlagMeta = {
  name: string;
  type: "bool" | "bool_with_date" | "text" | "single_select";
  label: string;
  date_field?: string;
  options?: string[];   // single_select only
  /** Optional richer display labels for single_select options. The stored
   * value stays `options[i]`; the dropdown shows option_labels[value] if set. */
  option_labels?: Record<string, string>;
  /** When present, the component opens a confirmation modal before the
   * PATCH fires. Used for high-stakes overrides (e.g. signing flags). */
  confirm?: ConfirmMeta;
};

type Props = {
  /** Record id of the entity being edited (property or landlord). */
  entityId?: string;
  /** Deprecated alias — kept so existing property call sites keep working. */
  propertyId?: string;
  /** The entity's current ``fields`` blob (Properties or Landlords record). */
  fields: Record<string, any>;
  /** Subset of catalog field names to render here. */
  show: string[];
  /** Optional card title — falls back to "Manual flags". */
  title?: string;
  /** Optional helper sentence below the title. */
  description?: string;
  /** Called with the freshly-updated subset after a successful PATCH so the
   * parent can refresh derived state (stage, gate-block reason, etc.). */
  onUpdated?: (updated: Record<string, any>) => void;
  /** Endpoint that returns the catalog (default: properties). */
  catalogPath?: string;
  /** PATCH endpoint that writes the values (default: properties). */
  patchPath?: string;
};

/**
 * Renders a card of agent-toggleable Properties fields. Each row's widget is
 * picked from the backend ``flags-catalog`` metadata — bool → checkbox,
 * bool_with_date → checkbox + date readout, text → text input.
 *
 * Writes go to ``PATCH /api/properties/{id}/flags`` with an allowlisted
 * subset, so an agent can't silently corrupt non-flag columns. The component
 * does optimistic updates and reverts on error.
 *
 * Used at multiple stages on PropertyDetail (4 → 8). Each call site declares
 * which fields it cares about via the ``show`` prop.
 */
export function PropertyFlags({
  entityId,
  propertyId,
  fields,
  show,
  title,
  description,
  onUpdated,
  catalogPath = "/api/properties/flags-catalog",
  patchPath,
}: Props) {
  const id = entityId ?? propertyId;
  if (!id) throw new Error("PropertyFlags requires entityId (or legacy propertyId).");
  const resolvedPatchPath = patchPath ?? `/api/properties/${id}/flags`;
  const confirm = useConfirm();

  const [catalog, setCatalog] = useState<FlagMeta[] | null>(null);
  // Local overrides — set on optimistic update, cleared on response.
  const [local, setLocal] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // Track text edits separately so users can type freely without firing
  // a PATCH per keystroke; commit on blur or Enter.
  const [textDraft, setTextDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    api.get<{ fields: FlagMeta[] }>(catalogPath)
      .then((r) => setCatalog(r.data.fields))
      .catch((e) => setErr(e?.response?.data?.detail ?? "Failed to load flags catalog"));
  }, [catalogPath]);

  const rows = useMemo(() => {
    if (!catalog) return [];
    const byName = new Map(catalog.map((m) => [m.name, m]));
    return show.map((name) => byName.get(name)).filter(Boolean) as FlagMeta[];
  }, [catalog, show]);

  if (!catalog) {
    return (
      <section className="card p-5">
        <h3 className="font-serif text-base font-semibold text-navy-700">{title ?? "Manual flags"}</h3>
        <p className="text-xs text-ink-muted mt-2">Loading…</p>
      </section>
    );
  }
  if (rows.length === 0) return null;

  function valueOf(name: string): any {
    return name in local ? local[name] : fields[name];
  }

  async function patch(name: string, raw: any) {
    // Gate behind the confirmation modal when the catalog declares one. We
    // only prompt on the "consequential" direction — for booleans that's
    // ticking, not unticking (re-clearing an accidental tick shouldn't
    // require a second confirmation).
    const meta = (catalog ?? []).find((m) => m.name === name);
    const needsConfirm = meta?.confirm && (
      meta.type === "single_select" || meta.type === "text" || !!raw
    );
    if (needsConfirm && meta?.confirm) {
      const ok = await confirm({
        title: meta.confirm.title,
        body: meta.confirm.body,
        confirmLabel: meta.confirm.confirmLabel,
        cancelLabel: meta.confirm.cancelLabel,
        tone: meta.confirm.tone,
      });
      if (!ok) return;
    }

    setBusy(name); setErr(null);
    // Optimistic local update
    setLocal((cur) => ({ ...cur, [name]: raw }));
    try {
      const { data } = await api.patch(resolvedPatchPath, { [name]: raw });
      // Sync local cache from the server's actual value (Airtable normalises
      // e.g. False as the key being absent — so we read whatever came back).
      const updated = data.updated ?? {};
      setLocal((cur) => ({ ...cur, ...updated }));
      onUpdated?.(updated);
    } catch (e: any) {
      // Revert optimistic update on failure
      setLocal((cur) => {
        const { [name]: _drop, ...rest } = cur;
        return rest;
      });
      setErr(e?.response?.data?.detail ?? "Update failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="card p-5 space-y-3">
      <header>
        <h3 className="font-serif text-base font-semibold text-navy-700">{title ?? "Manual flags"}</h3>
        {description && <p className="text-xs text-ink-muted mt-1">{description}</p>}
      </header>

      {err && (
        <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded px-2.5 py-1.5">
          {err}
        </div>
      )}

      <ul className="space-y-2.5">
        {rows.map((row) => {
          const value = valueOf(row.name);
          const isBusy = busy === row.name;

          if (row.type === "single_select") {
            const current = value ?? "";
            return (
              <li key={row.name} className="flex items-center gap-3">
                <label className="text-sm text-ink-soft min-w-[160px] shrink-0">{row.label}</label>
                <select
                  className="input text-sm flex-1"
                  value={current}
                  disabled={isBusy}
                  onChange={(e) => patch(row.name, e.target.value)}>
                  <option value="">—</option>
                  {(row.options ?? []).map((opt) => (
                    <option key={opt} value={opt}>{row.option_labels?.[opt] ?? opt}</option>
                  ))}
                </select>
                {isBusy && <span className="text-xs text-ink-muted shrink-0">Saving…</span>}
              </li>
            );
          }

          if (row.type === "text") {
            const draft = row.name in textDraft ? textDraft[row.name] : (value ?? "");
            return (
              <li key={row.name} className="flex items-center gap-3">
                <label className="text-sm text-ink-soft min-w-[160px] shrink-0">{row.label}</label>
                <input
                  className="input text-sm flex-1"
                  value={draft}
                  disabled={isBusy}
                  onChange={(e) => setTextDraft((c) => ({ ...c, [row.name]: e.target.value }))}
                  onBlur={() => {
                    const newVal = draft.trim();
                    if (newVal !== (value ?? "")) patch(row.name, newVal);
                    setTextDraft((c) => {
                      const { [row.name]: _d, ...rest } = c;
                      return rest;
                    });
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") e.currentTarget.blur();
                    if (e.key === "Escape") {
                      setTextDraft((c) => {
                        const { [row.name]: _d, ...rest } = c;
                        return rest;
                      });
                      e.currentTarget.blur();
                    }
                  }}
                  placeholder="—"
                />
              </li>
            );
          }

          // Both bool and bool_with_date render the same checkbox UI; the
          // latter also shows the auto-stamped date on the right.
          const checked = !!value;
          const dateValue = row.date_field
            ? (row.date_field in local ? local[row.date_field] : fields[row.date_field])
            : null;
          return (
            <li key={row.name} className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-sm text-ink-soft cursor-pointer flex-1">
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={isBusy}
                  onChange={(e) => patch(row.name, e.target.checked)}
                />
                <span>{row.label}</span>
              </label>
              {row.type === "bool_with_date" && (
                <span className="text-xs text-ink-muted shrink-0">
                  {dateValue
                    ? new Date(dateValue).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "2-digit" })
                    : "—"}
                </span>
              )}
              {isBusy && <span className="text-xs text-ink-muted shrink-0">Saving…</span>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
