import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { brand } from "../lib/brand";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const setSession = useAuth((s) => s.setSession);
  const nav = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      setSession({ token: data.token, email: data.email, name: data.name });
      nav("/agent");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Sign-in failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-h-screen grid place-items-center bg-cream-50 p-6"
      style={{
        // Same paper-tint hero treatment as the dashboard hero card — a
        // subtle radial gold wash on cream so the login feels like it
        // belongs to the same product, not a separate brand surface.
        backgroundImage:
          "radial-gradient(900px 500px at 100% 0%, rgba(201, 162, 76, 0.10), transparent 65%), radial-gradient(700px 400px at 0% 100%, rgba(0, 74, 173, 0.06), transparent 60%)",
      }}>
      <div className="w-full max-w-sm rounded-lg bg-white shadow-paper border border-cream-300 overflow-hidden">
        <div className="bg-navy-700 text-white px-6 py-7 text-center border-b-2 border-gold-500">
          <div className="mx-auto mb-3 h-12 w-12 rounded-md bg-white text-navy-700 grid place-items-center font-serif font-bold text-lg shadow-sm">PG</div>
          <h1 className="font-serif font-semibold text-xl tracking-wide">{brand.name}</h1>
          <p className="text-xs uppercase tracking-kicker text-cream-200 mt-1">Agent console</p>
        </div>
        <form className="p-7 space-y-4" onSubmit={submit}>
          <label className="block">
            <span className="label mb-1.5">Email</span>
            <input
              className="input"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label className="block">
            <span className="label mb-1.5">Password</span>
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}
          <button className="btn-primary w-full" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
