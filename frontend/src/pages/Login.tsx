import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { brand } from "../lib/brand";
import { supabase, supabaseEnabled } from "../lib/supabase";

// Google / Microsoft sign-in buttons are hidden unless VITE_ENABLE_OAUTH=true.
// Email + password works regardless (Supabase default, no provider setup).
const OAUTH_ENABLED = import.meta.env.VITE_ENABLE_OAUTH === "true";

/** Sign-in for agency users.
 *
 * Supabase mode (VITE_SUPABASE_URL set): email/password + Google + Microsoft.
 * Legacy mode: the single bootstrap account against the backend (dev only).
 */
export default function Login() {
  return (
    <div
      className="min-h-screen grid place-items-center bg-cream-50 p-6"
      style={{
        backgroundImage:
          "radial-gradient(900px 500px at 100% 0%, rgba(201, 162, 76, 0.10), transparent 65%), radial-gradient(700px 400px at 0% 100%, rgba(0, 74, 173, 0.06), transparent 60%)",
      }}>
      <div className="w-full max-w-sm rounded-lg bg-white shadow-paper border border-cream-300 overflow-hidden">
        <div className="bg-navy-700 text-white px-6 py-7 text-center border-b-2 border-gold-500">
          <div className="mx-auto mb-3 h-12 w-12 rounded-md bg-white text-navy-700 grid place-items-center font-serif font-bold text-lg shadow-sm">LA</div>
          <h1 className="font-serif font-semibold text-xl tracking-wide">{brand.name}</h1>
          <p className="text-xs uppercase tracking-kicker text-cream-200 mt-1">{brand.tagline}</p>
        </div>
        {supabaseEnabled ? <SupabaseLogin /> : <LegacyLogin />}
      </div>
    </div>
  );
}

function SupabaseLogin() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();

  async function oauth(provider: "google" | "azure") {
    setError(null);
    const { error } = await supabase!.auth.signInWithOAuth({
      provider,
      options: { redirectTo: `${window.location.origin}/agent` },
    });
    if (error) setError(error.message);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === "signup") {
        const { data, error } = await supabase!.auth.signUp({ email, password });
        if (error) throw error;
        if (!data.session) {
          setNotice("Check your inbox to confirm your email, then sign in.");
          return;
        }
      } else {
        const { error } = await supabase!.auth.signInWithPassword({ email, password });
        if (error) throw error;
      }
      nav("/agent");
    } catch (err: any) {
      setError(err?.message ?? "Sign-in failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-7 space-y-4">
      {OAUTH_ENABLED && (
        <>
          <div className="grid grid-cols-1 gap-2">
            <button type="button" onClick={() => oauth("google")}
              className="flex items-center justify-center gap-2.5 w-full rounded-md border border-cream-400 px-4 py-2.5 text-sm font-medium text-ink hover:bg-cream-100 transition">
              <GoogleIcon /> Continue with Google
            </button>
            <button type="button" onClick={() => oauth("azure")}
              className="flex items-center justify-center gap-2.5 w-full rounded-md border border-cream-400 px-4 py-2.5 text-sm font-medium text-ink hover:bg-cream-100 transition">
              <MicrosoftIcon /> Continue with Microsoft
            </button>
          </div>

          <div className="flex items-center gap-3 text-xs text-ink-muted">
            <div className="h-px bg-cream-300 flex-1" /> or with email <div className="h-px bg-cream-300 flex-1" />
          </div>
        </>
      )}

      <form className="space-y-4" onSubmit={submit}>
        <label className="block">
          <span className="label mb-1.5">Email</span>
          <input className="input" type="email" autoComplete="email"
            value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="block">
          <span className="label mb-1.5">Password</span>
          <input className="input" type="password"
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
        </label>
        {error && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}
        {notice && <p className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-3 py-2">{notice}</p>}
        <button className="btn-primary w-full" disabled={loading}>
          {loading ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"}
        </button>
      </form>

      <p className="text-center text-sm text-ink-muted">
        {mode === "signup" ? "Already have an account?" : "New to the platform?"}{" "}
        <button type="button" className="text-navy-700 font-medium hover:underline"
          onClick={() => { setMode(mode === "signup" ? "signin" : "signup"); setError(null); setNotice(null); }}>
          {mode === "signup" ? "Sign in" : "Create an account"}
        </button>
      </p>
    </div>
  );
}

function LegacyLogin() {
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
    <form className="p-7 space-y-4" onSubmit={submit}>
      <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
        Dev mode — Supabase auth not configured (set VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY).
      </p>
      <label className="block">
        <span className="label mb-1.5">Email</span>
        <input className="input" type="email" autoComplete="email"
          value={email} onChange={(e) => setEmail(e.target.value)} required />
      </label>
      <label className="block">
        <span className="label mb-1.5">Password</span>
        <input className="input" type="password" autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      {error && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}
      <button className="btn-primary w-full" disabled={loading}>
        {loading ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.6-.4-3.9z"/>
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15 19 12 24 12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/>
      <path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C36.9 39.2 44 34 44 24c0-1.3-.1-2.6-.4-3.9z"/>
    </svg>
  );
}

function MicrosoftIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 23 23" aria-hidden>
      <rect x="1" y="1" width="10" height="10" fill="#F25022"/>
      <rect x="12" y="1" width="10" height="10" fill="#7FBA00"/>
      <rect x="1" y="12" width="10" height="10" fill="#00A4EF"/>
      <rect x="12" y="12" width="10" height="10" fill="#FFB900"/>
    </svg>
  );
}
