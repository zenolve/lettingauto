import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ContractEditor, EditorHandle } from "../components/ContractEditor";
import { BackLink } from "../components/ui/BackLink";
import { api } from "../lib/api";
import { MERGE_DESCRIPTIONS } from "../lib/mergeFieldInfo";

type MergeField = { group: string; key: string; label: string };
type LibraryDoc = {
  id: string;
  name: string;
  stage: number;
  default_mode: SendMode;
  source: "library_file" | "master_doc";
  signers: string[];
  description: string;
};
type PrepareResp = {
  document: LibraryDoc;
  body_html: string;
  merge_fields: Record<string, any>;
  merge_field_catalogue: MergeField[];
  audience?: string[];
};

type SendMode = "sign" | "email_pdf" | "email_html";
type Recipient = { role: string; name: string; email: string; mandatory: boolean };
type Signature = {
  id: string;
  display_name: string;
  role: string;
  filename: string;
  created_at: string;
  size_bytes: number;
};

// /pg_sigN/ anchors the document body can use. Keep aligned with
// backend/app/services/pre_signatures.py:KNOWN_ANCHORS.
const KNOWN_ANCHORS = ["/pg_sig1/", "/pg_sig2/", "/pg_sig3/", "/pg_sig4/"];

const MODE_LABEL: Record<SendMode, string> = {
  sign: "Send for signature",
  email_pdf: "Send PDF by email",
  email_html: "Send as email",
};

const MODE_BLURB: Record<SendMode, string> = {
  sign: "Renders to PDF and routes to DocuSign — mandatory signers get an anchored signature field, CC recipients receive the envelope for visibility only.",
  email_pdf: "Renders to PDF, attaches it to an email with the cover text below as the body.",
  email_html: "Sends the editor body itself as the email — no PDF attachment.",
};

export default function LibraryEditor() {
  const { id: propertyId = "", docId = "" } = useParams();
  const nav = useNavigate();

  const [data, setData] = useState<PrepareResp | null>(null);
  const [html, setHtml] = useState<string>("");
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [mode, setMode] = useState<SendMode>("email_html");
  const [coverHtml, setCoverHtml] = useState<string>("");
  const [subject, setSubject] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<any>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [unresolved, setUnresolved] = useState<string[] | null>(null);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [signatures, setSignatures] = useState<Signature[]>([]);
  // Map of /pg_sigN/ anchor → chosen signature id. Unset slots fall back to
  // the first available signature on the backend.
  const [signatureChoices, setSignatureChoices] = useState<Record<string, string>>({});
  const handleRef = useRef<EditorHandle | null>(null);
  const [selectedAttribute, setSelectedAttribute] = useState<string | null>(null);
  const [fieldFilter, setFieldFilter] = useState("");

  useEffect(() => {
    api.get<PrepareResp>(`/api/library/${docId}/prepare/${propertyId}`)
      .then((r) => {
        setData(r.data);
        setHtml(interpolate(r.data.body_html, r.data.merge_fields));
        setMode(r.data.document.default_mode);
        setSubject(`${r.data.document.name} — ${r.data.merge_fields.property_address ?? ""}`);
        // Seed default recipients from the doc's signer roles. Default
        // mandatory=true so every seeded recipient signs; the agent toggles
        // off any who should be CC-only.
        // Seed recipients from the document's signers (sign docs) or, for
        // email docs with no signers, from the template's "Sends to" audience.
        // Each role's email is pre-filled from the system where we have it.
        const seedRoles = r.data.document.signers.length
          ? r.data.document.signers
          : (r.data.audience ?? []);
        setRecipients(seedRoles.map((role) => ({
          role,
          name: roleName(role, r.data.merge_fields),
          email: roleEmail(role, r.data.merge_fields),
          mandatory: true,
        })));
        // Sensible default cover for the email-pdf mode — signed off with the
        // sending agency's name (agency_name lives in the merge context).
        const ll = r.data.merge_fields.landlord_full_name ?? "";
        const agency = r.data.merge_fields.agency_name ?? r.data.merge_fields.brand_name ?? "";
        setCoverHtml(`<p>Dear ${ll || "[recipient]"},</p><p>Please find ${r.data.document.name} attached.</p><p>Kind regards,<br/>${agency}</p>`);
      })
      .catch((e) => setError(e?.response?.data?.detail ?? "Failed to load document"));
    // Signatures registry — load once on mount. System-wide so no
    // per-property variance.
    api.get<{ signatures: Signature[] }>("/api/signatures")
      .then((r) => {
        const sigs = r.data.signatures ?? [];
        setSignatures(sigs);
        // Pre-fill each slot with the first available signature so the agent
        // sees the default mapping immediately. They can override per-slot.
        if (sigs.length > 0) {
          setSignatureChoices((prev) => {
            const next = { ...prev };
            for (const anchor of KNOWN_ANCHORS) {
              if (!next[anchor]) next[anchor] = sigs[0].id;
            }
            return next;
          });
        }
      })
      .catch(() => setSignatures([]));
  }, [propertyId, docId]);

  // Which /pg_sigN/ anchors the current document body uses. Live — re-evaluates
  // on every keystroke so the dropdowns appear/disappear as the agent edits.
  const usedAnchors = useMemo(
    () => KNOWN_ANCHORS.filter((a) => html.includes(a)),
    [html],
  );

  const grouped = useMemo(() => {
    const map: Record<string, MergeField[]> = {};
    (data?.merge_field_catalogue ?? []).forEach((m) => (map[m.group] ||= []).push(m));
    return map;
  }, [data]);

  async function openPreview() {
    if (!data) return;
    setPreviewBusy(true); setError(null);
    // Open the tab synchronously up-front so the browser doesn't treat it as
    // a popup (some browsers block window.open from inside an awaited promise).
    const win = window.open("", "_blank");
    if (!win) {
      setError("Pop-up blocked — please allow pop-ups for this site to preview the document.");
      setPreviewBusy(false);
      return;
    }
    win.document.write("<title>Preparing preview…</title><body style='font-family:Inter,system-ui;padding:2rem;color:#3a3f47'>Rendering document…</body>");
    try {
      const { data: r } = await api.post(
        `/api/library/${docId}/preview/${propertyId}`,
        { body_html: html, signature_choices: signatureChoices },
      );
      setUnresolved(r.unresolved_tokens ?? []);
      // Replace the placeholder doc with the rendered HTML. document.open()
      // then write() avoids the blob-URL CORS sandbox restrictions some
      // browsers apply to about:blank windows.
      win.document.open();
      win.document.write(r.html);
      win.document.close();
    } catch (e: any) {
      win.close();
      setError(e?.response?.data?.detail ?? "Preview failed");
    } finally {
      setPreviewBusy(false);
    }
  }

  async function downloadPdf() {
    if (!data) return;
    setDownloadBusy(true); setError(null);
    try {
      const res = await api.post(
        `/api/library/${docId}/pdf/${propertyId}`,
        { body_html: html, signature_choices: signatureChoices },
        { responseType: "blob" },
      );
      // Prefer the filename from Content-Disposition if present, fall back to
      // a sensible default. Different servers/proxies format the header
      // slightly differently — handle both quoted and unquoted forms.
      const cd: string = res.headers["content-disposition"] ?? "";
      const match = cd.match(/filename="?([^"]+)"?/i);
      const fallback = `${data.document.name}.pdf`;
      const filename = match?.[1] ?? fallback;

      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Give the download a beat to start before revoking the blob URL.
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Download failed");
    } finally {
      setDownloadBusy(false);
    }
  }

  async function send() {
    if (!data) return;
    setBusy(true); setError(null); setDone(null);
    try {
      const payload: any = {
        mode,
        title: subject,
        body_html: html,
        recipients,
        signature_choices: signatureChoices,
      };
      if (mode === "email_pdf") payload.email_cover_html = coverHtml;
      const { data: r } = await api.post(`/api/library/${docId}/send/${propertyId}`, payload);
      setDone(r);
      setTimeout(() => nav(`/agent/properties/${propertyId}?stage=${data.document.stage}`), 2200);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Send failed");
    } finally {
      setBusy(false);
    }
  }

  function updateRecipient(i: number, patch: Partial<Recipient>) {
    setRecipients((cur) => cur.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  if (error && !data) return <div className="card p-4 bg-rose-50 text-rose-700">{error}</div>;
  if (!data) return <div>Loading…</div>;

  const placeholder = data.document.source === "master_doc";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6">
      <div className="space-y-4 min-w-0">
        <div>
          <BackLink to={`/agent/properties/${propertyId}?stage=${data.document.stage}`} label="Property" />
          <h1 className="text-2xl font-bold text-navy-700 mt-1">{data.document.name}</h1>
          <p className="text-sm text-slate-500">{data.document.description}</p>
          {placeholder && (
            <p className="text-xs mt-2 inline-block px-2 py-1 rounded bg-amber-50 text-amber-800 border border-amber-200">
              Placeholder content — replace with real text or merge fields before sending.
            </p>
          )}
        </div>

        <ContractEditor initialHtml={html} onChange={setHtml}
                        editorRef={(h) => { handleRef.current = h; }}
                        onSelectMergeField={setSelectedAttribute} />
        <p className="text-xs text-ink-muted">
          Highlighted text is a merge field — hover to see its attribute, or Ctrl/Cmd-click it to select it.
        </p>

        {mode === "email_pdf" && (
          <section className="card p-4">
            <h3 className="text-sm font-semibold text-slate-700 mb-2">Email cover</h3>
            <p className="text-xs text-slate-500 mb-2">This is the email body. The edited document above is attached as a PDF.</p>
            <textarea
              className="input w-full h-32 font-mono text-xs"
              value={coverHtml}
              onChange={(e) => setCoverHtml(e.target.value)}
            />
          </section>
        )}

        {done && (
          <div className="card p-4 bg-emerald-50 border-emerald-200 text-emerald-800">
            <strong>Sent ({MODE_LABEL[mode]}).</strong>{" "}
            {done.sent_to && done.sent_to.length > 0 && <>Delivered to {done.sent_to.join(", ")}.</>}
            {done.docuseal?.id && <> DocuSeal ref <code>{done.docuseal.id}</code>.</>}
            <div className="text-xs mt-1">Redirecting back to property…</div>
          </div>
        )}
        {error && <div className="card p-4 bg-rose-50 border-rose-200 text-rose-700">{error}</div>}
      </div>

      {/* Sticky on large screens — palette follows the user down long documents. */}
      <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
        {/* --- Send mode --- */}
        <section className="card p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-2">How to send</h3>
          <div className="space-y-2">
            {(["sign", "email_pdf", "email_html"] as SendMode[]).map((m) => (
              <label key={m} className="flex items-start gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="mode"
                  className="mt-1"
                  checked={mode === m}
                  onChange={() => setMode(m)}
                />
                <div>
                  <div className="text-sm font-medium text-slate-800">{MODE_LABEL[m]}</div>
                  <div className="text-xs text-slate-500">{MODE_BLURB[m]}</div>
                </div>
              </label>
            ))}
          </div>
        </section>

        {/* --- Subject --- */}
        <section className="card p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-2">
            {mode === "sign" ? "Envelope title" : "Email subject"}
          </h3>
          <input className="input w-full" value={subject} onChange={(e) => setSubject(e.target.value)} />
        </section>

        {/* --- Recipients / Signers --- */}
        <section className="card p-4">
          <div className="flex items-baseline justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-700">
              {mode === "sign" ? "Signers" : "Recipients"}
            </h3>
            {mode === "sign" && (
              <span className="text-xs text-ink-muted">
                Signing: {recipients.filter((r) => r.mandatory).length} · CC: {recipients.filter((r) => !r.mandatory).length}
              </span>
            )}
          </div>
          {mode === "sign" && (
            <p className="text-xs text-ink-muted mb-3">
              The 1st mandatory signer is anchored at <code>/sig1/</code> in the PDF,
              the 2nd at <code>/sig2/</code>. CC recipients receive the envelope but
              don't sign.
            </p>
          )}
          {usedAnchors.length > 0 && (
            <div className="bg-gold-200/40 border border-gold-300 rounded px-3 py-3 mb-3 space-y-2">
              <div className="text-xs font-medium text-gold-700">
                Agency signatures — {usedAnchors.length} slot{usedAnchors.length === 1 ? "" : "s"}
              </div>
              {signatures.length === 0 ? (
                <p className="text-xs text-rose-700">
                  No signatures installed.{" "}
                  <a href="/agent/signatures" className="underline">Add one</a> before sending.
                </p>
              ) : (
                usedAnchors.map((anchor) => (
                  <div key={anchor} className="flex items-center gap-2 text-xs">
                    <code className="text-gold-700 shrink-0">{anchor}</code>
                    <span className="text-ink-muted">→</span>
                    <select
                      className="input text-xs py-1"
                      value={signatureChoices[anchor] ?? signatures[0].id}
                      onChange={(e) => setSignatureChoices((prev) => ({ ...prev, [anchor]: e.target.value }))}>
                      {signatures.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.display_name}{s.role ? ` — ${s.role}` : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                ))
              )}
            </div>
          )}
          {recipients.map((r, i) => {
            const signerOrdinal = mode === "sign"
              ? recipients.slice(0, i + 1).filter((x) => x.mandatory).length
              : 0;
            const anchor = mode === "sign" && r.mandatory && signerOrdinal <= 2
              ? (signerOrdinal === 1 ? "/sig1/" : "/sig2/")
              : null;
            return (
              <div key={i} className="space-y-2 mb-3 border-b last:border-0 border-slate-100 pb-3 last:pb-0">
                <input className="input text-sm" value={r.role}
                       onChange={(e) => updateRecipient(i, { role: e.target.value })} placeholder="Role" />
                <input className="input text-sm" value={r.name}
                       onChange={(e) => updateRecipient(i, { name: e.target.value })} placeholder="Full name" />
                <input className="input text-sm" type="email" value={r.email}
                       onChange={(e) => updateRecipient(i, { email: e.target.value })} placeholder="Email" />
                {mode === "sign" && (
                  <div className="flex items-center justify-between gap-2">
                    <label className="flex items-center gap-2 text-xs text-ink-soft cursor-pointer">
                      <input
                        type="checkbox"
                        checked={r.mandatory}
                        onChange={(e) => updateRecipient(i, { mandatory: e.target.checked })}
                      />
                      Mandatory signature
                    </label>
                    {anchor ? (
                      <span className="text-[10px] uppercase tracking-kicker text-gold-700 bg-gold-200 px-2 py-0.5 rounded">
                        anchor {anchor}
                      </span>
                    ) : r.mandatory ? (
                      <span className="text-[10px] uppercase tracking-kicker text-rose-700 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded">
                        no anchor — add more anchor strings to this doc
                      </span>
                    ) : (
                      <span className="text-[10px] uppercase tracking-kicker text-ink-muted bg-cream-200 px-2 py-0.5 rounded">
                        cc
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => setRecipients((cur) => cur.filter((_, idx) => idx !== i))}
                      className="text-xs text-rose-700 hover:underline">
                      Remove
                    </button>
                  </div>
                )}
              </div>
            );
          })}
          <button
            type="button"
            className="btn-ghost text-sm"
            onClick={() => setRecipients([...recipients, {
              role: mode === "sign" ? "Signer" : "Recipient",
              name: "",
              email: "",
              mandatory: mode === "sign",
            }])}>
            + add {mode === "sign" ? "signer / CC" : "recipient"}
          </button>
        </section>

        {/* --- Selected attribute (from Ctrl/Cmd-click in the document) --- */}
        {selectedAttribute && (
          <section className="card p-4 border-l-4 border-l-gold-400">
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-sm font-semibold text-slate-700">Selected attribute</h3>
              <button type="button" className="text-xs text-ink-muted hover:underline"
                      onClick={() => setSelectedAttribute(null)}>clear</button>
            </div>
            <code className="text-sm text-navy-700 bg-navy-50 px-2 py-1 rounded inline-block">{selectedAttribute}</code>
            {(() => {
              const f = data.merge_field_catalogue.find((m) => m.key === selectedAttribute);
              return f ? <p className="text-xs text-slate-500 mt-2">{f.label} · {f.group}</p> : null;
            })()}
          </section>
        )}

        {/* --- Merge fields --- */}
        <section className="card p-4">
          <div className="flex items-baseline justify-between mb-1">
            <h3 className="text-sm font-semibold text-slate-700">Merge fields</h3>
            <span className="text-[11px] text-slate-400">{(data.merge_field_catalogue ?? []).length} attributes</span>
          </div>
          <p className="text-xs text-slate-500 mb-2">
            Click a field to insert its value at the cursor. Hover the ⓘ to see what it means.
          </p>
          <input
            className="input text-sm w-full mb-2"
            placeholder="Filter attributes…"
            value={fieldFilter}
            onChange={(e) => setFieldFilter(e.target.value)}
          />
          <div className="space-y-3 max-h-[45vh] overflow-y-auto">
            {Object.entries(grouped).map(([group, fields]) => {
              const q = fieldFilter.trim().toLowerCase();
              const shown = q
                ? fields.filter((f) => `${f.label} ${f.key} ${group}`.toLowerCase().includes(q))
                : fields;
              if (shown.length === 0) return null;
              return (
                <div key={group}>
                  <div className="text-xs uppercase tracking-wide text-slate-400 mb-1">{group}</div>
                  <ul className="space-y-0.5">
                    {shown.map((f) => {
                      const raw = data.merge_fields[f.key];
                      const val = raw != null && raw !== "" ? String(raw) : "";
                      return (
                        <li key={f.key} className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleRef.current?.insertMergeField(f.key, val || undefined)}
                            className="flex-1 min-w-0 text-left px-2 py-1 rounded hover:bg-navy-50">
                            <span className="flex items-center justify-between gap-2">
                              <span className="text-xs font-medium text-navy-700 truncate">{f.label}</span>
                              <span className="text-[11px] text-slate-500 truncate max-w-[46%] text-right" title={val}>
                                {val || "—"}
                              </span>
                            </span>
                          </button>
                          <span
                            title={MERGE_DESCRIPTIONS[f.key] ?? f.label}
                            aria-label={MERGE_DESCRIPTIONS[f.key] ?? f.label}
                            className="shrink-0 grid place-items-center w-4 h-4 rounded-full border border-slate-300 text-[9px] text-slate-500 cursor-help select-none">
                            i
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
        </section>

        {unresolved && unresolved.length > 0 && (
          <div className="card p-3 text-xs bg-amber-50 border-amber-200 text-amber-800">
            Preview opened in a new tab.{" "}
            {unresolved.length} unfilled token{unresolved.length === 1 ? "" : "s"}: {unresolved.slice(0, 5).join(", ")}{unresolved.length > 5 ? "…" : ""}
          </div>
        )}

        <div className="grid grid-cols-2 gap-2">
          <button className="btn-secondary" onClick={openPreview} disabled={previewBusy}>
            {previewBusy ? "Rendering…" : "Preview in new tab"}
          </button>
          <button className="btn-secondary" onClick={downloadPdf} disabled={downloadBusy}>
            {downloadBusy ? "Building PDF…" : "Download PDF"}
          </button>
        </div>
        <button className="btn-primary w-full" onClick={send} disabled={busy || recipients.length === 0}>
          {busy ? "Sending…" : MODE_LABEL[mode]}
        </button>
      </aside>
    </div>
  );
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
}

// Replace every {{token}} with a span that both DISPLAYS the value and REMEMBERS
// the attribute it came from (data-merge-key), so the editor can show it on
// hover / Ctrl-click. Unresolved tokens keep their {{key}} text inside the span
// so the backend can still fill them in at render time.
function interpolate(html: string, vars: Record<string, any>): string {
  return html.replace(/\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}/gi, (_, k) => {
    const has = vars[k] != null && vars[k] !== "";
    const display = has ? String(vars[k]) : `{{${k}}}`;
    return `<span data-merge-key="${k}" class="merge-field" title="${k}">${escapeHtml(display)}</span>`;
  });
}

function roleName(role: string, m: Record<string, any>): string {
  const r = role.toLowerCase();
  if (r.includes("landlord"))  return m.landlord_full_name ?? "";
  if (r.includes("guarantor")) return m.guarantor_name ?? "";
  if (r.includes("tenant"))    return m.tenant_full_name ?? "";
  return "";
}
function roleEmail(role: string, m: Record<string, any>): string {
  const r = role.toLowerCase();
  if (r.includes("landlord"))  return m.landlord_email ?? "";
  if (r.includes("guarantor")) return m.guarantor_email ?? "";
  if (r.includes("tenant"))    return m.tenant_email ?? "";
  return "";
}
