"""Agency billing — Stripe (one-time £50 per new tenancy).

Pricing: a single £50 one-time fee each time an agency starts a new tenancy
(at property take-on, PG_01). No subscriptions, no card-on-file.

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


def start_tenancy_checkout(agency_id: str, property_id: str, address: str) -> Optional[dict]:
    """Create the one-time £50 Checkout Session for a new tenancy.

    Returns ``{checkout_url, payment_id, session_id}``, or ``None`` when billing
    is disabled (no Stripe key) or the session couldn't be created.
    """
    if not billing_enabled():
        return None
    fee = settings.stripe_tenancy_setup_fee_pence
    description = (f"New tenancy setup fee — {address}").strip(" —") or "New tenancy setup fee"

    # Pending payment row. Created under the agency's scope, so the adapter
    # stamps agency_id automatically — that's our attribution.
    payment = at.create(at.TableNames.PAYMENTS, {
        "property_id": property_id,
        "payment_type": "tenancy_setup_fee",
        "amount": fee / 100.0,
        "currency": settings.stripe_currency,
        "status": "pending",
        "description": description,
    })

    stripe = _stripe()
    base = settings.frontend_base_url.rstrip("/")
    try:
        customer_id = ensure_customer(agency_id)
        session = stripe.checkout.Session.create(
            mode="payment",
            customer=customer_id,
            line_items=[{
                "price_data": {
                    "currency": settings.stripe_currency,
                    "product_data": {"name": description},
                    "unit_amount": fee,
                },
                "quantity": 1,
            }],
            success_url=f"{base}/agent/properties/{property_id}?payment=success",
            cancel_url=f"{base}/agent/properties/{property_id}?payment=cancelled",
            client_reference_id=payment["id"],
            metadata={"payment_id": payment["id"], "agency_id": agency_id,
                      "property_id": property_id, "kind": "tenancy_setup"},
        )
    except Exception as e:  # noqa: BLE001 — keep the row for audit, don't break take-on
        at.update(at.TableNames.PAYMENTS, payment["id"],
                  {"status": "failed", "description": f"{description} (Stripe error: {e})"})
        logger.error("billing.tenancy_checkout_failed agency=%s err=%s", agency_id, e)
        return None

    at.update(at.TableNames.PAYMENTS, payment["id"], {
        "stripe_checkout_session_id": session["id"],
        "stripe_customer_id": customer_id,
    })
    logger.info("billing.tenancy_checkout agency=%s property=%s session=%s",
                agency_id, property_id, session["id"])
    return {"checkout_url": session["url"], "payment_id": payment["id"], "session_id": session["id"]}


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
