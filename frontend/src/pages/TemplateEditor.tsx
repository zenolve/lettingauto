import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ContractEditor, EditorHandle } from "../components/ContractEditor";
import { api } from "../lib/api";

type Raw = {
  doc_id: string;
  name: string;
  stage: number;
  default_mode: "sign" | "email_pdf" | "email_html";
  signers: string[];
  body_html: string;
  is_placeholder: boolean;
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

  useEffect(() => {
    api.get<Raw>(`/api/library/${docId}/raw`)
      .then((r) => { setDoc(r.data); setHtml(r.data.body_html); })
      .catch((e) => setErr(e?.response?.data?.detail ?? "Failed to load template"));
  }, [docId]);

  async function save() {
    if (!doc) return;
    setBusy(true); setErr(null); setSaved(false);
    try {
      await api.put(`/api/library/${docId}/raw`, { body_html: html });
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
  );
}
