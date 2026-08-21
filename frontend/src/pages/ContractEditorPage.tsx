import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ContractEditor, EditorHandle } from "../components/ContractEditor";
import { api } from "../lib/api";

type MergeField = { group: string; key: string; label: string };
type Template = { key: string; name: string; signers: string[] };
type PrepareResp = {
  template: Template;
  body_html: string;
  merge_fields: Record<string, string>;
  merge_field_catalogue: MergeField[];
};

type Signer = { role: string; name: string; email: string };

export default function ContractEditorPage() {
  const { id = "", template = "" } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState<PrepareResp | null>(null);
  const [html, setHtml] = useState<string>("");
  const [signers, setSigners] = useState<Signer[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<any>(null);
  const handleRef = useRef<EditorHandle | null>(null);
  const [selectedAttribute, setSelectedAttribute] = useState<string | null>(null);

  useEffect(() => {
    api.get<PrepareResp>(`/api/contracts/${id}/prepare/${template}`)
      .then((r) => {
        setData(r.data);
        // Interpolate merge fields once on load — user can still edit anything.
        const interpolated = interpolate(r.data.body_html, r.data.merge_fields);
        setHtml(interpolated);
        // Seed signers from template + property merge data
        setSigners(r.data.template.signers.map((role) => ({
          role,
          name: roleName(role, r.data.merge_fields),
          email: roleEmail(role, r.data.merge_fields),
        })));
      })
      .catch((e) => setError(e?.response?.data?.detail ?? "Failed to load template"));
  }, [id, template]);

  const grouped = useMemo(() => {
    const map: Record<string, MergeField[]> = {};
    (data?.merge_field_catalogue ?? []).forEach((m) => {
      (map[m.group] ||= []).push(m);
    });
    return map;
  }, [data]);

  async function submit() {
    if (!data) return;
    setBusy(true); setError(null);
    try {
      const { data: r } = await api.post(`/api/contracts/${id}/submit`, {
        template_key: data.template.key,
        title: `${data.template.name} — ${data.merge_fields.property_address}`,
        body_html: html,
        submitters: signers,
      });
      setDone(r);
      setTimeout(() => nav(`/agent/properties/${id}`), 2000);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Submission failed");
    } finally {
      setBusy(false);
    }
  }

  if (error && !data) return <div className="card p-4 bg-rose-50 text-rose-700">{error}</div>;
  if (!data) return <div>Loading…</div>;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
      <div className="space-y-4 min-w-0">
        <div>
          <h1 className="text-2xl font-bold text-navy-700">{data.template.name}</h1>
          <p className="text-sm text-slate-500">
            Edit freely. Merge tokens like <code>{`{{landlord_full_name}}`}</code> are interpolated when the
            contract is rendered to PDF and sent to DocuSeal.
          </p>
        </div>
        <ContractEditor initialHtml={html} onChange={setHtml}
                        editorRef={(h) => { handleRef.current = h; }}
                        onSelectMergeField={setSelectedAttribute} />
        <p className="text-xs text-slate-500">
          Highlighted text is a merge field — hover to see its attribute, or Ctrl/Cmd-click it to select it.
        </p>
        {done && (
          <div className="card p-4 bg-emerald-50 border-emerald-200 text-emerald-800">
            Contract sent to DocuSeal. Signing email dispatched. Redirecting…
          </div>
        )}
        {error && (
          <div className="card p-4 bg-rose-50 border-rose-200 text-rose-700">{error}</div>
        )}
      </div>

      {/* Sticky on large screens so the merge-field palette follows the agent
          down the (long) document instead of forcing scroll-ups (UAT feedback). */}
      <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
        <section className="card p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-2">Signers</h3>
          {signers.map((s, i) => (
            <div key={i} className="space-y-2 mb-3 border-b last:border-0 border-slate-100 pb-3 last:pb-0">
              <input className="input text-sm" value={s.role}
                     onChange={(e) => updateSigner(i, { role: e.target.value })} placeholder="Role" />
              <input className="input text-sm" value={s.name}
                     onChange={(e) => updateSigner(i, { name: e.target.value })} placeholder="Full name" />
              <input className="input text-sm" type="email" value={s.email}
                     onChange={(e) => updateSigner(i, { email: e.target.value })} placeholder="Email" />
            </div>
          ))}
          <button className="btn-ghost text-sm" onClick={() => setSigners([...signers, { role: "", name: "", email: "" }])}>
            + add signer
          </button>
        </section>

        {selectedAttribute && (
          <section className="card p-4 border-l-4 border-l-gold-400">
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-sm font-semibold text-slate-700">Selected attribute</h3>
              <button type="button" className="text-xs text-slate-400 hover:underline"
                      onClick={() => setSelectedAttribute(null)}>clear</button>
            </div>
            <code className="text-sm text-navy-700 bg-navy-50 px-2 py-1 rounded inline-block">{selectedAttribute}</code>
            {(() => {
              const f = data.merge_field_catalogue.find((m) => m.key === selectedAttribute);
              return f ? <p className="text-xs text-slate-500 mt-2">{f.label} · {f.group}</p> : null;
            })()}
          </section>
        )}

        <section className="card p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-2">Merge fields</h3>
          <p className="text-xs text-slate-500 mb-2">Click to insert at cursor.</p>
          <div className="space-y-3 max-h-[40vh] overflow-y-auto">
            {Object.entries(grouped).map(([group, fields]) => (
              <div key={group}>
                <div className="text-xs uppercase tracking-wide text-slate-400 mb-1">{group}</div>
                <div className="flex flex-wrap gap-1">
                  {fields.map((f) => (
                    <button key={f.key} type="button"
                      onClick={() => {
                        const raw = data.merge_fields[f.key];
                        const val = raw != null && raw !== "" ? String(raw) : undefined;
                        handleRef.current?.insertMergeField(f.key, val);
                      }}
                      className="text-xs px-2 py-1 rounded border border-navy-200 bg-navy-50 text-navy-700 hover:bg-navy-100">
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <button className="btn-primary w-full" onClick={submit} disabled={busy}>
          {busy ? "Sending to DocuSeal…" : "Render PDF & send to DocuSeal"}
        </button>
      </aside>
    </div>
  );

  function updateSigner(i: number, patch: Partial<Signer>) {
    setSigners((cur) => cur.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  }
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
}

function interpolate(html: string, vars: Record<string, any>): string {
  return html.replace(/\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}/gi, (_, k) => {
    const display = vars[k] != null ? String(vars[k]) : `{{${k}}}`;
    return `<span data-merge-key="${k}" class="merge-field" title="${k}">${escapeHtml(display)}</span>`;
  });
}

function roleName(role: string, m: Record<string, string>): string {
  const r = role.toLowerCase();
  if (r.includes("landlord")) return m.landlord_full_name ?? "";
  if (r.includes("tenant"))   return m.tenant_full_name ?? "";
  return "";
}
function roleEmail(role: string, m: Record<string, string>): string {
  const r = role.toLowerCase();
  if (r.includes("landlord")) return m.landlord_email ?? "";
  if (r.includes("tenant"))   return m.tenant_email ?? "";
  return "";
}
