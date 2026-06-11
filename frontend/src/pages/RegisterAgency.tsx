import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { useAgency } from "../lib/agency";
import { signOut } from "../lib/auth";
import { brand } from "../lib/brand";

/** First-run screen for a signed-in user with no agency yet — Editorial Mesh. */
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
    <div className="min-h-screen bg-mesh-hero grid place-items-center p-6">
      <div className="w-full max-w-xl">
        <p className="kicker text-center mb-2">{brand.name}</p>

        <div className="card rounded-3xl overflow-hidden">
          <div className="px-8 pt-8">
            <h1 className="font-serif text-[32px] leading-tight font-semibold">
              Set up your <em>agency</em>.
            </h1>
            <p className="text-sm text-ink-soft mt-2.5 leading-relaxed">
              One agency per account — you'll be its owner. Branding, billing and
              details can all be fine-tuned later in Settings.
            </p>
          </div>

          <form className="px-8 pb-8 pt-6 space-y-4" onSubmit={submit}>
            <label className="block">
              <span className="label mb-1.5">Agency name <span aria-hidden className="text-rose-600">*</span></span>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Kensington Lettings Ltd" required minLength={2} autoFocus />
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <label className="block">
                <span className="label mb-1.5">Contact email</span>
                <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </label>
              <label className="block">
                <span className="label mb-1.5">Phone</span>
                <input className="input" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
              </label>
            </div>
            <label className="block">
              <span className="label mb-1.5">Office address</span>
              <input className="input" value={address} onChange={(e) => setAddress(e.target.value)} />
            </label>
            <label className="block">
              <span className="label mb-1.5">Website</span>
              <input className="input" type="url" value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://…" />
            </label>
            {error && (
              <p role="alert" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-xl px-3.5 py-2.5">
                {error}
              </p>
            )}
            <button className="btn-primary w-full" disabled={loading}>
              {loading ? "Creating…" : "Create agency"}
            </button>
            <p className="text-center text-xs text-ink-muted">
              Wrong account?{" "}
              <button type="button" className="text-ink underline underline-offset-4 hover:text-ink-soft"
                onClick={() => { signOut(); nav("/login"); }}>
                Sign out
              </button>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
