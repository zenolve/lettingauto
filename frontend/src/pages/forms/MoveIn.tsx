import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { BackLink } from "../../components/ui/BackLink";
import { api } from "../../lib/api";

export default function MoveIn() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  async function send() {
    setBusy(true); setErr(null);
    try {
      const { data } = await api.post(`/api/forms/tenant-pack/${id}`);
      setResult(data);
      setTimeout(() => nav(`/agent/properties/${id}`), 1500);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <header className="rounded-lg border border-cream-300 bg-white shadow-paper p-6 md:p-8"
        style={{ backgroundImage: "radial-gradient(600px 250px at 100% 0%, rgba(201, 162, 76, 0.07), transparent 60%)" }}>
        <BackLink to={`/agent/properties/${id}?stage=7`} label="Property — Stage 7" />
        <div className="kicker mt-2">Stage 7 · Pre-tenancy</div>
        <h1 className="mt-1">Send move-in pack</h1>
        <p className="mt-3 text-ink-soft max-w-2xl">
          Emails the tenant the prescribed documents (How To Rent, Gas Cert, EPC, EICR, TDS info, RRA for APT)
          and marks the relevant served-flags on the property.
        </p>
      </header>

      <div className="card p-6 space-y-4">
        <p className="text-ink-soft">
          Confirm all prerequisites are in place before sending — funds cleared, deposit registered, all certs on file.
          The gate to Stage 8 (Live Tenancy) will re-evaluate after submission.
        </p>
        {err && <div className="bg-rose-50 text-rose-700 p-3 rounded">{err}</div>}
        {result && <div className="bg-emerald-50 text-emerald-700 p-3 rounded">Pack sent. Redirecting…</div>}
        <button className="btn-primary" onClick={send} disabled={busy}>
          {busy ? "Sending…" : "Send tenant pack"}
        </button>
      </div>
    </div>
  );
}
