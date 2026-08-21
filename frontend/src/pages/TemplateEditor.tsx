import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ContractEditor, EditorHandle } from "../components/ContractEditor";
import { api } from "../lib/api";
import { MERGE_FIELDS } from "../lib/mergeFieldInfo";

const GROUPS = Array.from(new Set(MERGE_FIELDS.map((f) => f.group)));
const AUDIENCE_ROLES = ["Landlord", "Tenant", "Guarantor"];

type Raw = {
  doc_id: string;
  name: string;
  stage: number;
  default_mode: "sign" | "email_pdf" | "email_html";
  signers: string[];
  body_html: string;
  is_placeholder: boolean;
  audience: string[];
};

/**
 * Base-template editor — edits the underlying library document, NOT a
 * per-property send. Saving here updates `templates/library/{doc_id}.html`
 * so every future property send picks up the change. Per-property edits
 * still happen in LibraryEditor.
 */
export default function TemplateEditor() {
  const { docId = "" } = useParams();
  const nav = useNavigate();
  const [doc, setDoc] = useState<Raw | null>(null);
  const [html, setHtml] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const handleRef = useRef<EditorHandle | null>(null);
  const [fieldFilter, setFieldFilter] = useState("");
  const [audience, setAudience] = useState<string[]>([]);

  useEffect(() => {
    api.get<Raw>(`/api/library/${docId}/raw`)
      .then((r) => { setDoc(r.data); setHtml(r.data.body_html); setAudience(r.data.audience ?? []); })
      .catch((e) => setErr(e?.response?.data?.detail ?? "Failed to load template"));
  }, [docId]);

  async function save() {
    if (!doc) return;
    setBusy(true); setErr(null); setSaved(false);
    try {
      await api.put(`/api/library/${docId}/raw`, { body_html: html, audience });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Save failed");
    } finally {
      setBusy(false);
    }
  }

  if (err && !doc) return <div className="card p-4 text-rose-700 bg-rose-50">{err}</div>;
  if (!doc) return <div>Loading…</div>;

  return (
    <div className="space-y-4">
      <div>
        <Link to="/agent/library" className="text-sm text-navy-600 hover:underline">← Library</Link>
        <div className="flex items-baseline justify-between mt-1">
          <h1 className="text-2xl font-bold text-navy-700">{doc.name}</h1>
          <span className="text-xs px-2 py-1 rounded bg-navy-50 text-navy-700 border border-navy-200">
            Stage {doc.stage} · Base template
          </span>
        </div>
        <p className="text-sm text-slate-500">
          Edits to this template apply to every future per-property send. Existing per-property edits aren't
          retroactively changed. Use <code>{`{{merge_field}}`}</code> tokens (e.g. <code>{`{{landlord_full_name}}`}</code>,
          <code>{`{{property_address}}`}</code>) — they're interpolated at send time.
        </p>
        {doc.is_placeholder && (
          <p className="text-xs px-3 py-2 rounded bg-amber-50 text-amber-800 border border-amber-200 mt-2 inline-block">
            This is the master-doc placeholder. Saving will replace it with real content for every future use.
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-6">
        <div className="space-y-4 min-w-0">
          <ContractEditor initialHtml={html} onChange={setHtml}
                          editorRef={(h) => { handleRef.current = h; }} />

          {err && <div className="card p-4 bg-rose-50 border-rose-200 text-rose-700">{err}</div>}
          {saved && <div className="card p-4 bg-emerald-50 border-emerald-200 text-emerald-800">Template saved.</div>}

          <div className="flex gap-2 justify-end">
            <button className="btn-secondary" onClick={() => nav("/agent/library")}>Cancel</button>
            <button className="btn-primary" onClick={save} disabled={busy}>
              {busy ? "Saving…" : "Save base template"}
            </button>
          </div>
        </div>

        {/* --- Attribute palette --- */}
        <aside className="lg:sticky lg:top-4 lg:self-start space-y-4">
          <section className="card p-4">
            <h3 className="text-sm font-semibold text-slate-700 mb-1">Sends to</h3>
            <p className="text-xs text-slate-500 mb-2">
              Who this document is addressed to. When you send it for a property, that party's email is pre-filled from the system.
            </p>
            <div className="space-y-1.5">
              {AUDIENCE_ROLES.map((role) => (
                <label key={role} className="flex items-center gap-2 text-sm text-ink-soft cursor-pointer">
                  <input
                    type="checkbox"
                    checked={audience.includes(role)}
                    onChange={(e) =>
                      setAudience((cur) => (e.target.checked ? [...cur, role] : cur.filter((r) => r !== role)))
                    }
                  />
                  {role}
                </label>
              ))}
            </div>
            <p className="text-[11px] text-ink-muted mt-2">
              Leave all unticked for “fill in manually”. Click <strong>Save base template</strong> to store this.
            </p>
          </section>

          <section className="card p-4">
            <div className="flex items-baseline justify-between mb-1">
              <h3 className="text-sm font-semibold text-slate-700">Merge fields</h3>
              <span className="text-[11px] text-slate-400">{MERGE_FIELDS.length} attributes</span>
            </div>
            <p className="text-xs text-slate-500 mb-2">
              Click to drop a <code>{`{{token}}`}</code> in at the cursor. The grey text is a sample of what it produces; hover the ⓘ for what it means.
            </p>
            <input
              className="input text-sm w-full mb-2"
              placeholder="Filter attributes…"
              value={fieldFilter}
              onChange={(e) => setFieldFilter(e.target.value)}
            />
            <div className="space-y-3 max-h-[62vh] overflow-y-auto">
              {GROUPS.map((group) => {
                const q = fieldFilter.trim().toLowerCase();
                const shown = MERGE_FIELDS.filter(
                  (f) => f.group === group &&
                    (!q || `${f.label} ${f.key} ${f.group}`.toLowerCase().includes(q)),
                );
                if (shown.length === 0) return null;
                return (
                  <div key={group}>
                    <div className="text-xs uppercase tracking-wide text-slate-400 mb-1">{group}</div>
                    <ul className="space-y-0.5">
                      {shown.map((f) => (
                        <li key={f.key} className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleRef.current?.insertToken(f.key)}
                            className="flex-1 min-w-0 text-left px-2 py-1 rounded hover:bg-navy-50">
                            <span className="flex items-center justify-between gap-2">
                              <span className="text-xs font-medium text-navy-700 truncate">{f.label}</span>
                              <span className="text-[11px] text-slate-400 truncate max-w-[46%] text-right" title={f.sample}>
                                {f.sample}
                              </span>
                            </span>
                            <code className="block text-[10px] font-mono text-slate-400 truncate">{`{{${f.key}}}`}</code>
                          </button>
                          <span
                            title={f.description}
                            aria-label={f.description}
                            className="shrink-0 grid place-items-center w-4 h-4 rounded-full border border-slate-300 text-[9px] text-slate-500 cursor-help select-none">
                            i
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
