import { create } from "zustand";

const KEY = "pg_session";

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
  setSession: (s: Session | null) => void;
};

export const useAuth = create<AuthStore>((set) => ({
  session: load(),
  setSession: (s) => {
    save(s);
    set({ session: s });
  },
}));

export function getToken(): string | null {
  return useAuth.getState().session?.token ?? null;
}

export function signOut() {
  useAuth.getState().setSession(null);
}
