import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAgencyName } from "../lib/agency";
import { api, DashboardData } from "../lib/api";

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
const COLORS = {
  emerald: "#059669", amber: "#D97706", rose: "#E11D48",
  navy: "#1E3A5F", gold: "#C9A24C", slate: "#64748B", sky: "#0EA5E9",
};

function fmtGBP(n: number): string {
  return `£${Math.round(n).toLocaleString()}`;
}

function daysLabel(d: number): string {
  if (d === 0) return "today";
  if (d === 1) return "tomorrow";
  if (d < 0) return `${Math.abs(d)}d overdue`;
  return `in ${d}d`;
}

/** Urgency tone for a "days until" value. */
function urgency(d: number): "danger" | "warn" | "muted" {
  if (d <= 7) return "danger";
  if (d <= 30) return "warn";
  return "muted";
}

// ---------------------------------------------------------------------------
// Primitives (dependency-free)
// ---------------------------------------------------------------------------
type Tone = "danger" | "warn" | "info" | "good" | "neutral";
const TONE: Record<Tone, { num: string; ring: string; dot: string }> = {
  danger:  { num: "text-rose-700",    ring: "border-rose-200 bg-rose-50/60",       dot: "bg-rose-500" },
  warn:    { num: "text-amber-700",   ring: "border-amber-200 bg-amber-50/60",     dot: "bg-amber-500" },
  info:    { num: "text-navy-700",    ring: "border-cream-300 bg-white",           dot: "bg-navy-500" },
  good:    { num: "text-emerald-700", ring: "border-emerald-200 bg-emerald-50/60", dot: "bg-emerald-500" },
  neutral: { num: "text-ink",         ring: "border-cream-300 bg-white",           dot: "bg-slate-400" },
};

function StatCard({ label, value, tone = "neutral", hint, to }: {
  label: string; value: number | string; tone?: Tone; hint?: string; to?: string;
}) {
  const t = TONE[tone];
  const body = (
    <div className={`rounded-lg border ${t.ring} p-4 h-full ${to ? "hover:shadow-paper transition-shadow" : ""}`}>
      <div className="flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${t.dot}`} aria-hidden />
        <span className="text-xs uppercase tracking-wide text-ink-muted">{label}</span>
      </div>
      <div className={`mt-2 text-3xl font-serif font-semibold tabular-nums ${t.num}`}>{value}</div>
      {hint && <div className="text-xs text-ink-muted mt-1">{hint}</div>}
    </div>
  );
  return to ? <Link to={to} className="block focus:outline-none focus:ring-2 focus:ring-gold-400 rounded-lg">{body}</Link> : body;
}

function Section({ title, desc, right, children }: {
  title: string; desc?: string; right?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <section className="card p-5 md:p-6">
      <header className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="font-serif text-lg font-semibold text-navy-700">{title}</h2>
          {desc && <p className="text-sm text-ink-muted mt-0.5">{desc}</p>}
        </div>
        {right}
      </header>
      {children}
    </section>
  );
}

/** SVG donut + text legend (counts + %). Accessible: aria-label summarises,
 *  legend gives the numbers so it never relies on colour alone. */
function Donut({ data, size = 128, thickness = 18 }: {
  data: { label: string; value: number; color: string }[]; size?: number; thickness?: number;
}) {
  const total = data.reduce((s, d) => s + d.value, 0);
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  let offset = 0;
  const aria = `Breakdown: ${data.map((d) => `${d.label} ${d.value}`).join(", ")}`;
  return (
    <div className="flex items-center gap-5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={aria} className="shrink-0">
        <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#EFEBE3" strokeWidth={thickness} />
          {total > 0 && data.map((d, i) => {
            const len = (d.value / total) * c;
            const seg = (
              <circle key={i} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={d.color}
                strokeWidth={thickness} strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset} />
            );
            offset += len;
            return seg;
          })}
        </g>
        <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" className="fill-ink font-serif" fontSize={size * 0.26}>{total}</text>
      </svg>
      <ul className="space-y-1.5 text-sm min-w-0 flex-1">
        {data.map((d, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: d.color }} aria-hidden />
            <span className="text-ink-soft truncate">{d.label}</span>
            <span className="text-ink font-medium ml-auto tabular-nums">{d.value}</span>
            <span className="text-ink-muted text-xs w-9 text-right tabular-nums">{total ? Math.round((d.value / total) * 100) : 0}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StageBars({ rows }: { rows: DashboardData["pipeline"]["by_stage"] }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <ul className="space-y-1.5">
      {rows.map((r) => (
        <li key={r.order}>
          <Link to="/agent/properties" className="group flex items-center gap-3">
            <span className="w-28 shrink-0 text-xs text-ink-soft">
              <span className="font-medium text-ink tabular-nums">{r.order}</span> {r.name}
            </span>
            <span className="flex-1 h-5 rounded bg-cream-100 overflow-hidden">
              <span className="block h-full rounded bg-navy-500/80 group-hover:bg-navy-600 transition-colors"
                style={{ width: `${(r.count / max) * 100}%`, minWidth: r.count ? "6px" : "0" }} />
            </span>
            <span className="w-6 text-right text-sm tabular-nums text-ink">{r.count}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function UrgencyChip({ days }: { days: number }) {
  const u = urgency(days);
  const cls = u === "danger" ? "bg-rose-50 text-rose-700 border-rose-200"
    : u === "warn" ? "bg-amber-50 text-amber-700 border-amber-200"
    : "bg-cream-100 text-ink-muted border-cream-300";
  return <span className={`text-xs px-2 py-0.5 rounded-full border tabular-nums whitespace-nowrap ${cls}`}>{daysLabel(days)}</span>;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const agencyName = useAgencyName();

  useEffect(() => {
    api.get<DashboardData>("/api/dashboard")
      .then((r) => setData(r.data))
      .catch((e) => setErr(e?.response?.data?.detail ?? "Failed to load dashboard"));
  }, []);

  if (err) return <div className="card p-6 text-rose-700 bg-rose-50 border-rose-200">{err}</div>;
  if (!data) {
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Loading dashboard">
        <div className="h-8 w-56 bg-cream-200 rounded animate-pulse motion-reduce:animate-none" />
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-24 bg-cream-100 rounded-lg animate-pulse motion-reduce:animate-none" />)}
        </div>
        <div className="h-64 bg-cream-100 rounded-lg animate-pulse motion-reduce:animate-none" />
      </div>
    );
  }

  const { act_now, pipeline, compliance, upcoming, portfolio } = data;

  const tenancyDonut = Object.entries(portfolio.tenancy_type_split).map(([label, value], i) => ({
    label, value, color: [COLORS.navy, COLORS.gold, COLORS.sky, COLORS.slate][i % 4],
  }));
  const serviceDonut = Object.entries(portfolio.service_level_split).map(([label, value], i) => ({
    label, value, color: [COLORS.emerald, COLORS.gold, COLORS.sky, COLORS.slate, COLORS.navy][i % 5],
  }));
  const complianceDonut = [
    { label: "Compliant", value: compliance.breakdown.compliant, color: COLORS.emerald },
    { label: "Expiring soon", value: compliance.breakdown.expiring, color: COLORS.amber },
    { label: "Expired / missing", value: compliance.breakdown.bad, color: COLORS.rose },
  ];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="kicker">Today at {agencyName}</div>
          <h1 className="!text-h2 mt-1">Dashboard</h1>
          <p className="text-sm text-ink-muted mt-1">
            {pipeline.total} propert{pipeline.total === 1 ? "y" : "ies"} · {portfolio.active_tenancies} active ·
            managed rent roll {fmtGBP(portfolio.rent_roll_annual)}/yr
          </p>
        </div>
        <Link to="/agent/properties" className="btn-ghost text-navy-700">View all properties →</Link>
      </header>

      {/* ---- ACT NOW ---- */}
      <section aria-label="Needs attention">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <StatCard label="Gate-blocked" value={act_now.gate_blocked} tone={act_now.gate_blocked ? "danger" : "neutral"} to="/agent/properties" />
          <StatCard label="Offers pending" value={act_now.offers_pending} tone={act_now.offers_pending ? "warn" : "neutral"} hint="awaiting landlord" />
          <StatCard label="Certs ≤30 days" value={act_now.certs_expiring_30d} tone={act_now.certs_expiring_30d ? "danger" : "neutral"} hint="gas / EICR" />
          <StatCard label="Referencing" value={act_now.referencing_pending} tone={act_now.referencing_pending ? "warn" : "neutral"} hint="to chase" />
          <StatCard label="Move-in ready" value={act_now.movein_ready} tone={act_now.movein_ready ? "info" : "neutral"} hint="send pack" />
          <StatCard label="Overdue diary" value={act_now.overdue_diary} tone={act_now.overdue_diary ? "danger" : "neutral"} />
        </div>
      </section>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* ---- PIPELINE ---- */}
        <Section title="Pipeline" desc="Where every property sits right now">
          <StageBars rows={pipeline.by_stage} />
          <div className="mt-4 pt-4 border-t border-cream-200 grid grid-cols-3 gap-3 text-center">
            <div><div className="text-xl font-serif font-semibold text-ink tabular-nums">{pipeline.split.pre_tenancy}</div><div className="text-xs text-ink-muted">Pre-tenancy</div></div>
            <div><div className="text-xl font-serif font-semibold text-emerald-700 tabular-nums">{pipeline.split.active}</div><div className="text-xs text-ink-muted">Live</div></div>
            <div><div className="text-xl font-serif font-semibold text-ink tabular-nums">{pipeline.split.ending}</div><div className="text-xs text-ink-muted">Ending</div></div>
          </div>
        </Section>

        {/* ---- COMPLIANCE ---- */}
        <Section title="Compliance" desc="Certificate health across the book">
          <Donut data={complianceDonut} />
          <div className="mt-4 pt-4 border-t border-cream-200 flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <span className="text-ink-soft">EPC F/G (can't let): <strong className={compliance.epc_fg ? "text-rose-700" : "text-ink"}>{compliance.epc_fg}</strong></span>
            <span className="text-ink-soft">HMO licence unconfirmed: <strong className={compliance.hmo_unconfirmed ? "text-amber-700" : "text-ink"}>{compliance.hmo_unconfirmed}</strong></span>
          </div>
        </Section>
      </div>

      {/* ---- UPCOMING DATES ---- */}
      <Section title="Upcoming dates" desc="Diary alerts due in the next 30 days — prepare in advance"
        right={upcoming.overdue_count ? <span className="text-xs px-2 py-1 rounded-full bg-rose-50 text-rose-700 border border-rose-200">{upcoming.overdue_count} overdue</span> : undefined}>
        {upcoming.diary_agenda.length === 0 ? (
          <p className="text-sm text-ink-muted">Nothing due in the next 30 days.</p>
        ) : (
          <ul className="divide-y divide-cream-200">
            {upcoming.diary_agenda.map((d, i) => (
              <li key={i} className="py-2.5 flex items-center gap-3">
                <UrgencyChip days={d.days_until} />
                <span className="text-xs px-2 py-0.5 rounded bg-cream-100 text-ink-soft border border-cream-300 whitespace-nowrap">{d.type ?? "Diary"}</span>
                <span className="text-sm text-ink-soft truncate flex-1">{d.message ?? d.address}</span>
                {d.property_id && <Link to={`/agent/properties/${d.property_id}`} className="text-xs text-navy-600 hover:underline shrink-0">{d.address ?? "open"} →</Link>}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* ---- CERT EXPIRY RUNWAY ---- */}
        <Section title="Certificate runway" desc="Gas & EICR expiring in the next 90 days">
          {compliance.expiry_runway.length === 0 ? (
            <p className="text-sm text-ink-muted">No certificates expiring in the next 90 days.</p>
          ) : (
            <ul className="divide-y divide-cream-200">
              {compliance.expiry_runway.map((c, i) => (
                <li key={i} className="py-2.5 flex items-center gap-3">
                  <UrgencyChip days={c.days_left} />
                  <span className="text-xs px-2 py-0.5 rounded bg-cream-100 text-ink-soft border border-cream-300">{c.cert}</span>
                  <span className="text-sm text-ink-soft truncate flex-1">{c.address}</span>
                  <Link to={`/agent/properties/${c.property_id}`} className="text-xs text-navy-600 hover:underline shrink-0">open →</Link>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {/* ---- STALLED ---- */}
        <Section title="Stalled deals" desc={`Same stage for more than 14 days`}>
          {pipeline.stalled.length === 0 ? (
            <p className="text-sm text-ink-muted">Nothing stalled — the pipeline is moving.</p>
          ) : (
            <ul className="divide-y divide-cream-200">
              {pipeline.stalled.map((s) => (
                <li key={s.property_id} className="py-2.5 flex items-center gap-3">
                  <span className="text-xs px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 tabular-nums whitespace-nowrap">{s.days_stuck}d</span>
                  <span className="text-sm text-ink-soft truncate flex-1">{s.address}</span>
                  <span className="text-xs text-ink-muted shrink-0">Stage {s.stage_order} · {s.stage_name}</span>
                  <Link to={`/agent/properties/${s.property_id}`} className="text-xs text-navy-600 hover:underline shrink-0">open →</Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      {/* ---- PORTFOLIO ---- */}
      <Section title="Portfolio" desc="Your active book at a glance">
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 items-start">
          <div className="space-y-3">
            <div>
              <div className="text-3xl font-serif font-semibold text-ink tabular-nums">{fmtGBP(portfolio.rent_roll_monthly)}</div>
              <div className="text-xs text-ink-muted">Managed rent roll / month</div>
            </div>
            <div>
              <div className="text-xl font-serif font-semibold text-emerald-700 tabular-nums">{portfolio.active_tenancies}</div>
              <div className="text-xs text-ink-muted">Active tenancies</div>
            </div>
          </div>

          <div>
            <div className="text-xs uppercase tracking-wide text-ink-muted mb-2">Tenancy type</div>
            {tenancyDonut.length ? <Donut data={tenancyDonut} size={104} thickness={15} /> : <p className="text-sm text-ink-muted">No data.</p>}
          </div>

          <div>
            <div className="text-xs uppercase tracking-wide text-ink-muted mb-2">Service level</div>
            {serviceDonut.length ? <Donut data={serviceDonut} size={104} thickness={15} /> : <p className="text-sm text-ink-muted">No data.</p>}
          </div>

          <div>
            <div className="text-xs uppercase tracking-wide text-ink-muted mb-2">Offers</div>
            {Object.keys(portfolio.offer_conversion).length === 0 ? (
              <p className="text-sm text-ink-muted">No offers recorded yet.</p>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {Object.entries(portfolio.offer_conversion).map(([k, v]) => (
                  <li key={k} className="flex items-center gap-2">
                    <span className="text-ink-soft truncate">{k.replace(/_/g, " ")}</span>
                    <span className="text-ink font-medium ml-auto tabular-nums">{v}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Section>
    </div>
  );
}
