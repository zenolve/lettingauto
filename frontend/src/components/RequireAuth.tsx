import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function RequireAuth({ children }: { children: JSX.Element }) {
  const session = useAuth((s) => s.session);
  const loc = useLocation();
  if (!session) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }
  return children;
}
