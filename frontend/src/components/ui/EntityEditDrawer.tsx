import { useEffect, useState } from "react";

/** Field metadata as served by the backend catalogs
 * (/api/tenants/fields-catalog, /api/landlords/flags-catalog,
 * /api/properties/flags-catalog). */
export type FieldSpec = {
  name: string;
  label: string;
  type: "text" | "email" | "date" | "number" | "int" | "bool" | "single_select" | "bool_with_date";
  options?: string[];
  group?: string;
};

type Props = {
  title: string;
  subtitle?: string;
  fields: FieldSpec[];
  values: Record<string, any>;
  open: boolean;
  onClose: () => void;
  /** Receives only the fields the user actually changed. */
  onSave: (changed: Record<string, any>) => Promise<void>;
};

/** Right-hand slide-over for editing one entity (tenant / landlord / property).
 * Generic over the backend field catalogs so adding a field server-side is all
 * that's needed to expose it here. */
export default function EntityEditDrawer({ title, subtitle, fields, values, open, onClose, onSave }: Props) {
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setDraft({});
      setError(null);
    }
  }, [open, values]);

  if (!open) return null;

  const current = (name: string) => (name in draft ? draft[name] : values[name]);

  async function save() {
    if (Object.keys(draft).length === 0) {
      onClose();
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(draft);
      onClose();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : detail?.message ?? "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <aside className="absolute right-0 top-0 h-full w-full max-w-md bg-white shadow-2xl flex flex-col">
        <header className="px-6 py-5 border-b border-cream-300 bg-cream-50">
          <h2 className="font-serif text-xl text-navy-700">{title}</h2>
          {subtitle && <p className="text-xs text-ink-muted mt-0.5">{subtitle}</p>}
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {fields.map((f) => (
            <Field key={f.name} spec={f} value={current(f.name)}
              onChange={(v) => setDraft((d) => ({ ...d, [f.name]: v }))} />
          ))}
        </div>

        <footer className="px-6 py-4 border-t border-cream-300 bg-cream-50 space-y-2">
          {error && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}
          <div className="flex justify-between items-center">
            <span className="text-xs text-ink-muted">
              {Object.keys(draft).length} change{Object.keys(draft).length === 1 ? "" : "s"}
            </span>
            <div className="flex gap-2">
              <button className="px-4 py-2 rounded-md border border-cream-400 text-sm hover:bg-cream-100 transition"
                onClick={onClose}>
                Cancel
              </button>
              <button className="btn-primary px-5" onClick={save} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </footer>
      </aside>
    </div>
  );
}

function Field({ spec, value, onChange }: { spec: FieldSpec; value: any; onChange: (v: any) => void }) {
  if (spec.type === "bool" || spec.type === "bool_with_date") {
    return (
      <label className="flex items-center justify-between gap-3 py-1 cursor-pointer">
        <span className="text-sm text-ink">{spec.label}</span>
        <input type="checkbox" className="h-4 w-4 accent-navy-700"
          checked={!!value} onChange={(e) => onChange(e.target.checked)} />
      </label>
    );
  }
  if (spec.type === "single_select") {
    return (
      <label className="block">
        <span className="label mb-1.5">{spec.label}</span>
        <select className="input" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
          <option value="">—</option>
          {(spec.options ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>
    );
  }
  const inputType =
    spec.type === "date" ? "date"
    : spec.type === "number" || spec.type === "int" ? "number"
    : spec.type === "email" ? "email"
    : "text";
  return (
    <label className="block">
      <span className="label mb-1.5">{spec.label}</span>
      <input className="input" type={inputType}
        step={spec.type === "int" ? 1 : undefined}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
