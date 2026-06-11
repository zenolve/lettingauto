import { create } from "zustand";

import { supabase, supabaseEnabled } from "./supabase";

const KEY = "la_session";

type Session = { token: string; email: string; name: string };

function load(): Session | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

function save(s: Session | null) {
  if (!s) localStorage.removeItem(KEY);
  else localStorage.setItem(KEY, JSON.stringify(s));
}

type AuthStore = {
  session: Session | null;
  /** False until the Supabase session restore has completed (supabase mode). */
  ready: boolean;
  setSession: (s: Session | null) => void;
  setReady: (r: boolean) => void;
};

export const useAuth = create<AuthStore>((set) => ({
  // In supabase mode the session comes from supabase-js (restored async);
  // the localStorage copy is only the legacy bootstrap session.
  session: supabaseEnabled ? null : load(),
  ready: !supabaseEnabled,
  setSession: (s) => {
    if (!supabaseEnabled) save(s);
    set({ session: s });
  },
  setReady: (r) => set({ ready: r }),
}));

function sessionFromSupabase(sbSession: any): Session | null {
  if (!sbSession) return null;
  const user = sbSession.user ?? {};
  const meta = user.user_metadata ?? {};
  return {
    token: sbSession.access_token,
    email: user.email ?? "",
    name: meta.full_name ?? meta.name ?? user.email ?? "Agent",
  };
}

/** Hydrate auth at app boot: restore the Supabase session and track refreshes
 * so getToken() always returns a live access token. No-op in legacy mode. */
export function initAuth() {
  if (!supabase) return;
  supabase.auth.getSession().then(({ data }) => {
    useAuth.getState().setSession(sessionFromSupabase(data.session));
    useAuth.getState().setReady(true);
  });
  supabase.auth.onAuthStateChange((_event, sbSession) => {
    useAuth.getState().setSession(sessionFromSupabase(sbSession));
    useAuth.getState().setReady(true);
  });
}

export function getToken(): string | null {
  return useAuth.getState().session?.token ?? null;
}

export function signOut() {
  if (supabase) void supabase.auth.signOut();
  useAuth.getState().setSession(null);
}
