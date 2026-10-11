"""Agency billing — Stripe (one-time £50 per new tenancy).

Pricing: a single £50 one-time fee each time an agency starts a new tenancy -
at property take-on (PG_01), or when re-letting a property whose previous
tenancy has ended (PG_RL). No subscriptions, no card-on-file.

Flow:
  1. Take-on creates the property, then ``start_tenancy_checkout`` creates a
     pending ``payments`` row (agency-scoped, so it carries ``agency_id``) and a
     one-time Stripe Checkout Session for £50. The payment-row id is set as both
     the session ``metadata.payment_id`` AND ``client_reference_id``, so the
     payment can be matched back from the webhook either way. The take-on
     response returns the hosted checkout URL.
  2. The agent pays on Stripe's page; the ``checkout.session.completed`` webhook
     (routers/payments.py) flips that payment row to ``succeeded``. Because the
     row was created under the agency's scope, "which agency paid" is answered
     automatically — the row already carries ``agency_id``.

With ``STRIPE_SECRET_KEY`` unset, billing is disabled: ``start_tenancy_checkout``
returns ``None`` and take-on proceeds free (dev).
"""
from __future__ import annotations

from typing import Any, Optional

from app.config import settings
from app.core.logger import get_logger
from app.db import supabase_client as at

logger = get_logger(__name__)


class BillingUnavailable(Exception):
    """Stripe couldn't create the checkout — surface as 502 to the caller."""


def billing_enabled() -> bool:
    return bool(settings.stripe_secret_key)


def _stripe():
    import stripe  # local import — keep dev installs light
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _agency(agency_id: str) -> dict:
    return at.get(at.TableNames.AGENCIES, agency_id)


def ensure_customer(agency_id: str) -> str:
    """Get-or-create the agency's Stripe customer (groups its payments under
    one customer in the Stripe dashboard); returns the customer id."""
    agency = _agency(agency_id)
    f = agency.get("fields", {})
    if f.get("stripe_customer_id"):
        return f["stripe_customer_id"]
    stripe = _stripe()
    customer = stripe.Customer.create(
        name=f.get("name"),
        email=f.get("billing_email") or f.get("email"),
        metadata={"agency_id": agency_id},
    )
    at.update(at.TableNames.AGENCIES, agency_id, {"stripe_customer_id": customer["id"]})
    logger.info("billing.customer_created agency=%s customer=%s", agency_id, customer["id"])
    return customer["id"]


def _open_checkout(
    agency_id: str, payment_id: str, *, description: str, success_url: str, cancel_url: str, kind: str,
) -> tuple[Any, str]:
    """One-time tenancy-fee Checkout Session for a pending payments row.

    The payment-row id is both ``client_reference_id`` and
    ``metadata.payment_id`` so the webhook can match it either way.
    Returns ``(session, customer_id)``.
    """
    stripe = _stripe()
    customer_id = ensure_customer(agency_id)
    session = stripe.checkout.Session.create(
        mode="payment",
        customer=customer_id,
        line_items=[{
            "price_data": {
                "currency": settings.stripe_currency,
                "product_data": {"name": description},
                "unit_amount": settings.stripe_tenancy_setup_fee_pence,
            },
            "quantity": 1,
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=payment_id,
        metadata={"payment_id": payment_id, "agency_id": agency_id, "kind": kind},
    )
    return session, customer_id


# ---------------------------------------------------------------------------
# Pay-first take-on (deferred fulfillment)
#
# Nothing is created in the pipeline until the £50 clears:
#   1. ``create_takeon_intent`` snapshots the validated take-on payload onto a
#      pending payments row (the "intent") and opens a Checkout Session.
#   2. ``mark_paid_and_fulfill`` runs from BOTH the Stripe webhook and the
#      success-redirect poller; a compare-and-set on the payment's status
#      (pending → succeeded) guarantees exactly one of them creates the
#      property. The loser just reads the winner's result.
# ---------------------------------------------------------------------------
def create_takeon_intent(agency_id: str, payload: dict) -> Optional[dict]:
    """Store the take-on payload as a pending intent + open the £50 checkout.

    Returns ``{payment_id, checkout_url}``; ``None`` when billing is disabled
    (caller should fulfil immediately). Raises on Stripe failure — with
    pay-first there is nothing to salvage, the agent simply retries.
    """
    if not billing_enabled():
        return None
    fee = settings.stripe_tenancy_setup_fee_pence
    address = (payload.get("address") or "").strip()
    description = (f"New tenancy setup fee — {address}").strip(" —") or "New tenancy setup fee"

    # The intent: a pending payment row carrying the form payload. Created
    # under the agency's scope, so agency_id is stamped automatically.
    payment = at.create(at.TableNames.PAYMENTS, {
        "payment_type": "tenancy_setup_fee",
        "amount": fee / 100.0,
        "currency": settings.stripe_currency,
        "status": "pending",
        "description": description,
        "metadata": {"takeon_payload": payload},
    })

    base = settings.frontend_base_url.rstrip("/")
    try:
        session, customer_id = _open_checkout(
            agency_id, payment["id"], description=description,
            success_url=f"{base}/agent/takeon/complete?payment={payment['id']}",
            cancel_url=f"{base}/agent/properties/new?payment=cancelled&payment_id={payment['id']}",
            kind="tenancy_setup",
        )
    except Exception as e:  # noqa: BLE001
        at.update(at.TableNames.PAYMENTS, payment["id"],
                  {"status": "failed", "description": f"{description} (Stripe error: {e})"})
        logger.error("billing.takeon_intent_failed agency=%s err=%s", agency_id, e)
        raise BillingUnavailable(f"Could not start the Stripe checkout: {e}") from e

    at.update(at.TableNames.PAYMENTS, payment["id"], {
        "stripe_checkout_session_id": session["id"],
        "stripe_customer_id": customer_id,
        # Stored so an abandoned checkout can be resumed from the form page
        # (sessions stay payable for 24h).
        "metadata": {"takeon_payload": payload, "checkout_url": session["url"]},
    })
    logger.info("billing.takeon_intent agency=%s payment=%s session=%s",
                agency_id, payment["id"], session["id"])
    return {"payment_id": payment["id"], "checkout_url": session["url"]}


async def mark_paid_and_fulfill(payment: dict) -> Optional[str]:
    """Idempotent fulfillment: flip the intent to paid and create the property.

    Called from the webhook AND the status poller. The status CAS
    (pending → succeeded) makes fulfillment exactly-once: only the winner runs
    ``handle_takeon``. Returns the property_id (winner), the already-linked
    property_id (loser/late call), or None if the row wasn't pending.
    """
    if (payment.get("fields", {}).get("metadata") or {}).get("relet"):
        return await _fulfil_relet_intent(payment)

    pid = payment["id"]
    f = payment.get("fields", {})
    existing = f.get("property_id")
    if existing:
        return existing

    won = at.try_transition(at.TableNames.PAYMENTS, pid, "status", "pending", "succeeded")
    if not won:
        # Someone else is fulfilling (or already has) — report their result.
        try:
            return at.get(at.TableNames.PAYMENTS, pid, fresh=True).get("fields", {}).get("property_id")
        except Exception:  # noqa: BLE001
            return None

    payload = (f.get("metadata") or {}).get("takeon_payload")
    if not payload:
        logger.error("billing.fulfill_no_payload payment=%s", pid)
        return None

    # Fulfil under the intent's agency scope so every row the handler writes
    # is isolated + branded correctly (the webhook runs unscoped).
    from app.handlers.pg01_takeon import handle_takeon  # noqa: PLC0415 — avoid load cycle
    from app.models.common import PropertyTakeonInput  # noqa: PLC0415
    scope = at.set_agency_scope(f.get("agency_id"))
    try:
        result = await handle_takeon(PropertyTakeonInput(**payload))
        property_id = result["property_id"]
        at.update(at.TableNames.PAYMENTS, pid, {"property_id": property_id})
        logger.info("billing.fulfilled payment=%s property=%s", pid, property_id)
        return property_id
    except Exception as e:  # noqa: BLE001 — money taken but fulfillment failed:
        # keep status=succeeded (true: they paid), flag the error for the
        # status endpoint / support. The poller surfaces it to the agent.
        logger.error("billing.fulfill_failed payment=%s err=%s", pid, e)
        try:
            meta = dict(f.get("metadata") or {})
            meta["fulfillment_error"] = str(e)[:300]
            at.update(at.TableNames.PAYMENTS, pid, {"metadata": meta})
        except Exception:  # noqa: BLE001
            pass
        return None
    finally:
        at.reset_agency_scope(scope)


# ---------------------------------------------------------------------------
# Pay-first re-let (PG_RL) - a new tenancy on a property whose last one ended
#
# Same pattern as take-on, one difference: the property already exists, so the
# payment row carries ``property_id`` from the start (it lists on the
# property's payments) and fulfilment is marked by ``metadata.relet.tenancy_id``.
# ---------------------------------------------------------------------------
def create_relet_intent(agency_id: str, property_id: str, address: str, *, requested_by: str) -> dict:
    """Open the tenancy-fee checkout for re-letting. Raises on Stripe failure."""
    fee = settings.stripe_tenancy_setup_fee_pence
    description = (f"New tenancy setup fee (re-let) — {address}").strip(" —") or "New tenancy setup fee (re-let)"
    relet = {"property_id": property_id, "requested_by": requested_by}
    payment = at.create(at.TableNames.PAYMENTS, {
        "payment_type": "tenancy_setup_fee",
        "amount": fee / 100.0,
        "currency": settings.stripe_currency,
        "status": "pending",
        "description": description,
        "property_id": property_id,
        "metadata": {"relet": relet},
    })
    base = settings.frontend_base_url.rstrip("/")
    try:
        session, customer_id = _open_checkout(
            agency_id, payment["id"], description=description,
            success_url=f"{base}/agent/takeon/complete?payment={payment['id']}&kind=relet",
            cancel_url=f"{base}/agent/properties/{property_id}?stage=9&payment=cancelled",
            kind="tenancy_relet",
        )
    except Exception as e:  # noqa: BLE001
        at.update(at.TableNames.PAYMENTS, payment["id"],
                  {"status": "failed", "description": f"{description} (Stripe error: {e})"})
        logger.error("billing.relet_intent_failed agency=%s property=%s err=%s", agency_id, property_id, e)
        raise BillingUnavailable(f"Could not start the Stripe checkout: {e}") from e

    at.update(at.TableNames.PAYMENTS, payment["id"], {
        "stripe_checkout_session_id": session["id"],
        "stripe_customer_id": customer_id,
        "metadata": {"relet": relet, "checkout_url": session["url"]},
    })
    logger.info("billing.relet_intent agency=%s property=%s payment=%s", agency_id, property_id, payment["id"])
    return {"payment_id": payment["id"], "checkout_url": session["url"]}


def relet_payments(property_id: str) -> tuple[Optional[dict], Optional[dict]]:
    """This property's re-let fees: (the latest open checkout, a fee that was
    paid but whose re-let hasn't completed). Either may be None."""
    rows = at.search(at.TableNames.PAYMENTS, at.eq("property_id", property_id), fresh=True)
    relets = [r for r in rows if (r.get("fields", {}).get("metadata") or {}).get("relet")]
    relets.sort(key=lambda r: r.get("createdTime") or "", reverse=True)
    open_pay = next((r for r in relets if r["fields"].get("status") == "pending"), None)
    paid = next((r for r in relets if r["fields"].get("status") == "succeeded"
                 and not r["fields"]["metadata"]["relet"].get("tenancy_id")), None)
    return open_pay, paid


def checkout_state(payment: dict) -> str:
    """'paid' | 'open' | 'expired' | 'unknown' for an intent's Checkout Session."""
    sid = payment.get("fields", {}).get("stripe_checkout_session_id")
    if not (billing_enabled() and sid):
        return "unknown"
    try:
        session = _stripe().checkout.Session.retrieve(sid)
    except Exception as e:  # noqa: BLE001
        logger.warning("billing.checkout_state_failed payment=%s err=%s", payment.get("id"), e)
        return "unknown"
    if session.get("payment_status") == "paid":
        return "paid"
    return "open" if session.get("status") == "open" else "expired"


async def _fulfil_relet_intent(payment: dict) -> Optional[str]:
    """Exactly-once fulfilment of a paid re-let intent (webhook + poller race)."""
    relet = (payment.get("fields", {}).get("metadata") or {}).get("relet") or {}
    property_id = relet.get("property_id")
    if relet.get("tenancy_id"):
        return property_id
    if not at.try_transition(at.TableNames.PAYMENTS, payment["id"], "status", "pending", "succeeded"):
        return property_id            # the other path won and is fulfilling
    return property_id if await fulfil_relet(payment) else None


async def fulfil_relet(payment: dict) -> Optional[dict]:
    """Run the re-let a paid fee bought; record the outcome on the payment.

    Also the retry path: a fee that was paid but whose re-let failed is
    fulfilled again here without charging again.
    """
    from app.services.tenancies import perform_relet  # noqa: PLC0415 — avoid load cycle

    f = payment.get("fields", {})
    meta = dict(f.get("metadata") or {})
    relet = dict(meta.get("relet") or {})
    scope = at.set_agency_scope(f.get("agency_id"))
    try:
        result = perform_relet(relet["property_id"], by=relet.get("requested_by") or "agent")
    except Exception as e:  # noqa: BLE001 — money taken but re-let failed: keep it findable
        logger.error("billing.relet_fulfil_failed payment=%s err=%s", payment["id"], e)
        meta["fulfillment_error"] = str(e)[:300]
        try:
            at.update(at.TableNames.PAYMENTS, payment["id"], {"metadata": meta})
        except Exception:  # noqa: BLE001
            pass
        return None
    else:
        meta["relet"] = {**relet, "tenancy_id": result["tenancy_id"]}
        meta.pop("fulfillment_error", None)
        at.update(at.TableNames.PAYMENTS, payment["id"], {"metadata": meta})
        logger.info("billing.relet_fulfilled payment=%s property=%s tenancy=%s",
                    payment["id"], relet["property_id"], result["tenancy_id"])
        return result
    finally:
        at.reset_agency_scope(scope)


def verify_session_paid(payment: dict) -> bool:
    """Ask Stripe whether the intent's Checkout Session is actually paid —
    used by the success-redirect poller so we never trust the URL alone."""
    sid = payment.get("fields", {}).get("stripe_checkout_session_id")
    if not (billing_enabled() and sid):
        return False
    try:
        session = _stripe().checkout.Session.retrieve(sid)
        return session.get("payment_status") == "paid"
    except Exception as e:  # noqa: BLE001
        logger.warning("billing.verify_session_failed payment=%s err=%s", payment.get("id"), e)
        return False


def billing_summary(agency_id: str) -> dict[str, Any]:
    """Shape the Settings → Billing card: pricing + tenancy-fee payment counts."""
    try:
        rows = at.search(
            at.TableNames.PAYMENTS,
            at.and_(at.eq("agency_id", agency_id), at.eq("payment_type", "tenancy_setup_fee")),
            fresh=True,
        )
    except Exception:  # noqa: BLE001
        rows = []
    paid = sum(1 for r in rows if r.get("fields", {}).get("status") == "succeeded")
    pending = sum(1 for r in rows if r.get("fields", {}).get("status") == "pending")
    return {
        "enabled": billing_enabled(),
        "pricing": {
            "tenancy_setup_fee": settings.stripe_tenancy_setup_fee_pence / 100.0,
            "currency": settings.stripe_currency,
        },
        "tenancy_fees_paid": paid,
        "tenancy_fees_pending": pending,
    }
