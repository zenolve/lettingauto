import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api";
import { STAGES } from "../lib/stages";

type LibraryDoc = {
  id: string;
  name: string;
  stage: number;
  default_mode: "sign" | "email_pdf" | "email_html";
  source: "library_file" | "master_doc";
  signers: string[];
  description: string;
  has_real_content: boolean;
};

const MODE_BADGE: Record<LibraryDoc["default_mode"], { label: string; cls: string }> = {
  sign:       { label: "Sign",      cls: "bg-violet-50 text-violet-700 border-violet-200" },
  email_pdf:  { label: "Email PDF", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  email_html: { label: "Email",     cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
};

/**
 * Library index page — browse every TPL + library file without picking a
 * property first. Clicking a doc opens the *base template* editor, where
 * edits propagate to every future per-property send.
 */
export default function LibraryIndex() {
  const [docs, setDocs] = useState<LibraryDoc[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.get<{ documents: LibraryDoc[] }>(`/api/library`)
      .then((r) => setDocs(r.data.documents))
      .catch((e) => setErr(e?.response?.data?.detail ?? "Failed to load library"));
  }, []);

  const filtered = useMemo(() => {
    if (!docs) return null;
    const n = q.trim().toLowerCase();
    if (!n) return docs;
    return docs.filter((d) => [d.name, d.id, d.description].some((v) => (v ?? "").toLowerCase().includes(n)));
  }, [docs, q]);

  const grouped = useMemo(() => {
    if (!filtered) return new Map<number, LibraryDoc[]>();
    const m = new Map<number, LibraryDoc[]>();
    for (const d of filtered) (m.get(d.stage) ?? m.set(d.stage, []).get(d.stage)!).push(d);
    return m;
  }, [filtered]);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-3">
        <div>
          <Link to="/agent" className="text-sm text-navy-600 hover:underline">← Dashboard</Link>
          <h1 className="text-2xl font-bold text-navy-700 mt-1">Document library</h1>
          <p className="text-sm text-slate-500">
            Every TPL and contract template. Click any document to edit the <strong>base template</strong> —
            changes apply to every future per-property send.
          </p>
        </div>
        <input className="input max-w-xs" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {err && <div className="card p-4 text-rose-700 bg-rose-50">{err}</div>}
      {!docs && !err && <div className="card p-4 text-slate-500">Loading…</div>}

      <div className="space-y-6">
        {STAGES.map((stage) => {
          const rows = grouped.get(stage.order);
          if (!rows || rows.length === 0) return null;
          return (
            <section key={stage.order} className="card p-5">
              <header className="mb-3">
                <h2 className="text-sm uppercase tracking-wide text-navy-700">
                  Stage {stage.order} · {stage.name}
                </h2>
                <p className="text-xs text-slate-500">{stage.blurb}</p>
              </header>
              <ul className="divide-y divide-slate-100">
                {rows.map((d) => (
                  <li key={d.id} className="py-2">
                    <Link
                      to={`/agent/library/${d.id}`}
                      className="flex items-start gap-3 -mx-2 px-2 py-1 rounded hover:bg-slate-50">
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-slate-800 truncate">{d.name}</div>
                        <div className="text-xs text-slate-500 truncate">{d.description}</div>
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <span className={`text-[10px] px-2 py-0.5 rounded border ${MODE_BADGE[d.default_mode].cls}`}>
                          {MODE_BADGE[d.default_mode].label}
                        </span>
                        {!d.has_real_content && (
                          <span className="text-[10px] px-2 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200">
                            Placeholder
                          </span>
                        )}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
