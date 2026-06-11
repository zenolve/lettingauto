import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function RequireAuth({ children }: { children: JSX.Element }) {
  const session = useAuth((s) => s.session);
  const ready = useAuth((s) => s.ready);
  const loc = useLocation();
  // Supabase restores its session asynchronously at boot — don't bounce to
  // /login while that's still in flight.
  if (!ready) {
    return (
      <div className="min-h-screen grid place-items-center bg-cream-50">
        <div className="text-sm text-ink-muted animate-pulse">Signing you in…</div>
      </div>
    );
  }
  if (!session) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }
  return children;
}
