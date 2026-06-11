import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { useAgency } from "../lib/agency";
import { signOut } from "../lib/auth";
import { brand } from "../lib/brand";

/** First-run screen for a signed-in user with no agency yet: register the
 * agency and become its owner. */
export default function RegisterAgency() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [website, setWebsite] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const loadAgency = useAgency((s) => s.load);
  const nav = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.post("/api/agencies/register", {
        name,
        email: email || undefined,
        phone: phone || undefined,
        office_address: address || undefined,
        website: website || undefined,
      });
      await loadAgency(true);
      nav("/agent");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : detail?.message ?? "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-h-screen grid place-items-center bg-cream-50 p-6"
      style={{
        backgroundImage:
          "radial-gradient(900px 500px at 100% 0%, rgba(201, 162, 76, 0.10), transparent 65%), radial-gradient(700px 400px at 0% 100%, rgba(0, 74, 173, 0.06), transparent 60%)",
      }}>
      <div className="w-full max-w-lg rounded-lg bg-white shadow-paper border border-cream-300 overflow-hidden">
        <div className="bg-navy-700 text-white px-7 py-6 border-b-2 border-gold-500">
          <p className="text-xs uppercase tracking-kicker text-cream-200">{brand.name}</p>
          <h1 className="font-serif font-semibold text-2xl mt-1">Set up your agency</h1>
          <p className="text-sm text-cream-200 mt-1.5">
            One agency per account. You'll be the owner and can fine-tune
            branding, billing and details later in Settings.
          </p>
        </div>
        <form className="p-7 space-y-4" onSubmit={submit}>
          <label className="block">
            <span className="label mb-1.5">Agency name *</span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Kensington Lettings Ltd" required minLength={2} />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="block">
              <span className="label mb-1.5">Contact email</span>
              <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="block">
              <span className="label mb-1.5">Phone</span>
              <input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </label>
          </div>
          <label className="block">
            <span className="label mb-1.5">Office address</span>
            <input className="input" value={address} onChange={(e) => setAddress(e.target.value)} />
          </label>
          <label className="block">
            <span className="label mb-1.5">Website</span>
            <input className="input" value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://…" />
          </label>
          {error && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}
          <button className="btn-primary w-full" disabled={loading}>
            {loading ? "Creating…" : "Create agency"}
          </button>
          <p className="text-center text-xs text-ink-muted">
            Wrong account?{" "}
            <button type="button" className="text-navy-700 hover:underline"
              onClick={() => { signOut(); nav("/login"); }}>
              Sign out
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}
