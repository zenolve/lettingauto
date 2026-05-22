import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, PropertySummary } from "../lib/api";

function formatAddedDate(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  // dd Mmm — short enough to fit in the column without dropping context.
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "2-digit" });
}

function GatePill({ status }: { status?: string }) {
  if (!status) return <span className="pill-neutral">—</span>;
  if (status === "Clear") return <span className="pill-clear">● Clear</span>;
  if (status === "Blocked") return <span className="pill-blocked">● Blocked</span>;
  return <span className="pill-await">{status}</span>;
}

function HeroStats({ rows }: { rows: PropertySummary[] }) {
  // Compute hero figures from the live list — agents see what matters today,
  // not a marketing graphic.
  const total = rows.length;
  const blocked = rows.filter((r) => r.gate_status === "Blocked").length;
  const tcSigned = rows.filter((r) => r.tc_signed).length;
  const taSigned = rows.filter((r) => r.ta_ll_signed && r.ta_tt_signed).length;
  return (
    <section
      className="rounded-lg border border-cream-300 bg-white shadow-paper p-6 md:p-8 mb-8"
      style={{
        backgroundImage:
          "radial-gradient(600px 250px at 100% 0%, rgba(201, 162, 76, 0.07), transparent 60%)",
      }}>
      <div className="kicker">Today at Palace Gate</div>
      <h1 className="mt-2">Properties under management</h1>
      <p className="mt-3 text-ink-soft max-w-2xl">
        {total} active record{total === 1 ? "" : "s"} · sorted by most recently added · blockers
        surfaced inline so they don't hide.
      </p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-6">
        <div className="stat"><div className="stat-num">{total}</div><div className="stat-lbl">Properties</div></div>
        <div className="stat"><div className="stat-num">{blocked}</div><div className="stat-lbl">Gate-blocked</div></div>
        <div className="stat"><div className="stat-num">{tcSigned}</div><div className="stat-lbl">T&amp;C signed</div></div>
        <div className="stat"><div className="stat-num">{taSigned}</div><div className="stat-lbl">TA fully signed</div></div>
      </div>
    </section>
  );
}

type Sort = "newest" | "oldest" | "address";

export default function Dashboard() {
  const [rows, setRows] = useState<PropertySummary[]>([]);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<Sort>("newest");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.get<PropertySummary[]>("/api/properties/")
      .then((r) => setRows(r.data))
      .catch((e) => setErr(e.response?.data?.detail ?? "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let result = !needle ? rows : rows.filter((r) =>
      [r.address, r.post_code, r.tenancy_type, r.service_level]
        .filter(Boolean)
        .some((v) => v!.toLowerCase().includes(needle)),
    );
    // Backend already returns newest-first by createdTime, but re-sort here
    // so the toggle is responsive without an extra fetch.
    result = [...result];
    if (sort === "newest") result.sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
    else if (sort === "oldest") result.sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
    else if (sort === "address") result.sort((a, b) => (a.address ?? "").localeCompare(b.address ?? ""));
    return result;
  }, [rows, q, sort]);

  return (
    <div className="space-y-6">
      <HeroStats rows={rows} />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="!text-h2">All properties</h2>
          <p className="text-sm text-ink-muted mt-1">Click any row to open the property detail.</p>
        </div>
        <div className="flex gap-2">
          <input
            className="input max-w-xs"
            placeholder="Search by address, postcode…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select className="input max-w-[170px]" value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort order">
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="address">By address</option>
          </select>
          <Link to="/agent/properties/new" className="btn-gold">+ New property</Link>
        </div>
      </div>

      {err && <div className="card p-4 text-rose-700 bg-rose-50 border-rose-200">{err}</div>}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-cream-100 text-ink-muted">
            <tr className="text-left">
              <th className="px-5 py-3 font-medium text-xs uppercase tracking-kicker">Address</th>
              <th className="px-4 py-3 font-medium text-xs uppercase tracking-kicker">Tenancy</th>
              <th className="px-4 py-3 font-medium text-xs uppercase tracking-kicker">Service</th>
              <th className="px-4 py-3 font-medium text-xs uppercase tracking-kicker">Gate</th>
              <th className="px-4 py-3 font-medium text-xs uppercase tracking-kicker">T&amp;C</th>
              <th className="px-4 py-3 font-medium text-xs uppercase tracking-kicker">TA</th>
              <th className="px-4 py-3 font-medium text-xs uppercase tracking-kicker">Added</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-cream-300">
            {loading ? (
              <tr><td colSpan={8} className="p-8 text-center text-ink-muted">Loading…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={8} className="p-8 text-center text-ink-muted">No properties yet.</td></tr>
            ) : filtered.map((p) => (
              <tr key={p.id} className="hover:bg-cream-100 transition-colors">
                <td className="px-5 py-4">
                  <div className="font-serif text-base font-medium text-ink">{p.address}</div>
                  <div className="text-xs text-ink-muted mt-0.5">{p.post_code ?? "—"}</div>
                </td>
                <td className="px-4 py-4 text-ink-soft">{p.tenancy_type ?? "—"}</td>
                <td className="px-4 py-4 text-ink-soft">{p.service_level || "—"}</td>
                <td className="px-4 py-4"><GatePill status={p.gate_status} /></td>
                <td className="px-4 py-4 text-ink-soft">{p.tc_signed ? "✓" : "—"}</td>
                <td className="px-4 py-4 text-ink-soft">{p.ta_ll_signed && p.ta_tt_signed ? "✓" : (p.ta_ll_signed || p.ta_tt_signed ? "½" : "—")}</td>
                <td className="px-4 py-4 text-ink-muted text-xs whitespace-nowrap">{formatAddedDate(p.created_at)}</td>
                <td className="px-4 py-4 text-right">
                  <Link to={`/agent/properties/${p.id}`} className="btn-ghost text-navy-700">Open →</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
