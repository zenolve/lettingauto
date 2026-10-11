import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../lib/api";

type TakeonStatus = {
  payment_id: string;
  kind?: "takeon" | "relet";
  status: "pending" | "succeeded" | "cancelled" | "failed" | string;
  fulfilled: boolean;
  property_id: string | null;
  checkout_url: string | null;
  fulfillment_error?: string | null;
};

/** Landing page after Stripe Checkout for a pay-first take-on or re-let.
 *
 * Polls the intent status: the tenancy is set up by whichever of the Stripe
 * webhook / this poller confirms payment first (exactly-once server-side).
 * On fulfillment → straight to the property page.
 */
export default function TakeonComplete() {
  const [params] = useSearchParams();
  const paymentId = params.get("payment");
  // Re-let: the property already exists; the fee archives the ended tenancy.
  const relet = params.get("kind") === "relet";
  const nav = useNavigate();
  const [state, setState] = useState<TakeonStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tries = useRef(0);

  useEffect(() => {
    if (!paymentId) {
      setError("Missing payment reference in the URL.");
      return;
    }
    let stop = false;
    let timer: number | undefined;

    async function poll() {
      if (stop) return;
      tries.current += 1;
      try {
        const { data } = await api.get<TakeonStatus>(`/api/forms/takeon-status/${paymentId}`);
        if (stop) return;
        setState(data);
        if (data.fulfilled && data.property_id) {
          nav(`/agent/properties/${data.property_id}`, { replace: true });
          return;
        }
        if (data.status === "cancelled" || data.status === "failed" || data.fulfillment_error) {
          return; // terminal — render the message below
        }
      } catch (e: any) {
        if (stop) return;
        setError(e?.response?.data?.detail ?? "Could not check the payment status.");
        return;
      }
      // Payment confirmation usually lands within a few seconds; back off a
      // little and give up nudging after ~2 minutes (webhook still completes
      // it server-side — the property list will show it).
      const delay = tries.current < 10 ? 1500 : 4000;
      if (tries.current < 40) timer = window.setTimeout(poll, delay);
    }

    void poll();
    return () => { stop = true; if (timer) window.clearTimeout(timer); };
  }, [paymentId, nav]);

  const terminalCancel = state?.status === "cancelled" || state?.status === "failed";
  const fulfillError = state?.fulfillment_error;
  const stillWaiting = !error && !terminalCancel && !fulfillError;

  return (
    <div className="max-w-lg mx-auto mt-16">
      <div className="card p-8 text-center space-y-4">
        {stillWaiting && (
          <>
            <div className="mx-auto h-12 w-12 rounded-full border-4 border-cream-300 border-t-navy-700 animate-spin" />
            <h1 className="font-serif text-2xl text-navy-700">Confirming your payment…</h1>
            <p className="text-sm text-ink-soft">
              {relet
                ? "Stripe has your £50 tenancy fee. We're archiving the previous tenancy and opening the property for new offers — this takes a few seconds. Don't close this tab."
                : "Stripe has your £50 tenancy fee. We're creating the property and notifying the landlord — this takes a few seconds. Don't close this tab."}
            </p>
            {tries.current > 12 && (
              <p className="text-xs text-ink-muted">
                Taking longer than usual — it will finish in the background; the
                property will appear in <Link className="text-navy-700 underline" to="/agent/properties">Properties</Link>.
              </p>
            )}
          </>
        )}

        {terminalCancel && (
          <>
            <h1 className="font-serif text-2xl text-navy-700">Payment not completed</h1>
            <p className="text-sm text-ink-soft">
              {relet
                ? <>The checkout was {state?.status}. Nothing was changed and nothing was charged — the tenancy is still ended.</>
                : <>The checkout was {state?.status}. No property was created and nothing was charged.</>}
            </p>
            {relet && state?.property_id
              ? <Link to={`/agent/properties/${state.property_id}?stage=9`} className="btn-primary inline-block">Back to the property</Link>
              : <Link to="/agent/properties/new" className="btn-primary inline-block">Start again</Link>}
          </>
        )}

        {fulfillError && (
          <>
            <h1 className="font-serif text-2xl text-navy-700">Payment received — setup hit a snag</h1>
            <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-2">
              {relet
                ? <>Your £50 was charged but the re-let failed: {fulfillError}. Use Re-let on the property
                    again — you won't be charged twice. Payment reference <code>{paymentId}</code>.</>
                : <>Your £50 was charged but creating the property failed: {fulfillError}.
                    Contact support with payment reference <code>{paymentId}</code> — nothing is lost.</>}
            </p>
            {relet && state?.property_id && (
              <Link to={`/agent/properties/${state.property_id}?stage=9`} className="btn-primary inline-block">Back to the property</Link>
            )}
          </>
        )}

        {error && (
          <>
            <h1 className="font-serif text-2xl text-navy-700">Something went wrong</h1>
            <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>
            <Link to="/agent/properties" className="btn-primary inline-block">Back to properties</Link>
          </>
        )}
      </div>
    </div>
  );
}
