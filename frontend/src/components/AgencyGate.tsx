import { useEffect } from "react";
import { Navigate } from "react-router-dom";

import { useAgency } from "../lib/agency";
import OnboardingModal from "./OnboardingModal";

/** Loads the signed-in user's agency before the agent app renders.
 *
 * - No membership yet → route to the agency-registration screen.
 * - First visit (onboarding incomplete) → product-tour modal overlays the app.
 */
export function AgencyGate({ children }: { children: JSX.Element }) {
  const status = useAgency((s) => s.status);
  const load = useAgency((s) => s.load);

  useEffect(() => {
    void load();
  }, [load]);

  if (status === "no_agency") {
    return <Navigate to="/register-agency" replace />;
  }
  if (status === "idle" || status === "loading") {
    return (
      <div className="min-h-screen grid place-items-center bg-cream-50">
        <div className="text-sm text-ink-muted animate-pulse">Loading your agency…</div>
      </div>
    );
  }
  // status ready (or error — render the app; individual calls surface errors)
  return (
    <>
      {children}
      <OnboardingModal />
    </>
  );
}
