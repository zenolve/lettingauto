"""Agency billing — Stripe.

Commercial pricing model:
  * £50 one-time fee each time an agency starts a NEW tenancy (charged when a
    property is taken on, i.e. PG_01).
  * £5 / month for each LIVE tenancy — one Stripe subscription per agency on a
    per-unit recurring Price (``STRIPE_PRICE_LIVE_TENANCY``); the subscription
    quantity tracks the agency's live-tenancy count (TA signed by all
    parties). Quantity syncs on gate advances and daily via the scheduler.

Flow:
  1. Agency registers → Stripe Customer created lazily.
  2. Agency adds a card via a Checkout session in ``setup`` mode
     (``create_setup_checkout``). The ``checkout.session.completed`` webhook
     attaches the payment method as the customer default and creates the
     £5/unit subscription at quantity 0.
  3. Each take-on calls ``charge_tenancy_setup_fee`` — an invoice item +
     immediately-paid invoice against the default card. Failure blocks the
     take-on with a 402.

With ``STRIPE_SECRET_KEY`` unset, billing is disabled: every gate is a no-op
so the product works end-to-end in dev without Stripe.
"""
from __future__ import annotations

from typing import Any, Optional

from app.config import settings
from app.core.logger import get_logger
from app.db import supabase_client as at

logger = get_logger(__name__)

PRICING = {
    "tenancy_setup_fee_pence": None,  # filled from settings at import below
    "live_tenancy_monthly_pence": 500,
    "currency": "gbp",
}


class BillingError(Exception):
    """A billing problem the caller should surface (usually as HTTP 402)."""

    def __init__(self, message: str, *, code: str = "billing_error") -> None:
        super().__init__(message)
        self.code = code


def billing_enabled() -> bool:
    return bool(settings.stripe_secret_key)


def _stripe():
    import stripe  # local import — keep dev installs light
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _agency(agency_id: str) -> dict:
    return at.get(at.TableNames.AGENCIES, agency_id)


# ---------------------------------------------------------------------------
# Customer / payment method / subscription
# ---------------------------------------------------------------------------
def ensure_customer(agency_id: str) -> str:
    """Get-or-create the agency's Stripe customer; returns the customer id."""
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


def create_setup_checkout(agency_id: str) -> str:
    """Checkout session (mode=setup) for the agency to add a card; returns URL."""
    if not billing_enabled():
        raise BillingError("Stripe is not configured on this server.", code="billing_disabled")
    customer_id = ensure_customer(agency_id)
    stripe = _stripe()
    base = settings.frontend_base_url.rstrip("/")
    session = stripe.checkout.Session.create(
        mode="setup",
        customer=customer_id,
        payment_method_types=["card"],
        success_url=f"{base}/settings?billing=success",
        cancel_url=f"{base}/settings?billing=cancelled",
        metadata={"agency_id": agency_id, "kind": "billing_setup"},
    )
    return session["url"]


def handle_setup_completed(session: dict) -> None:
    """checkout.session.completed (mode=setup): attach the collected payment
    method as the customer default, then start the live-tenancy subscription."""
    agency_id = (session.get("metadata") or {}).get("agency_id")
    if not agency_id:
        return
    stripe = _stripe()
    setup_intent_id = session.get("setup_intent")
    customer_id = session.get("customer")
    if setup_intent_id and customer_id:
        si = stripe.SetupIntent.retrieve(setup_intent_id)
        pm = si.get("payment_method")
        if pm:
            stripe.Customer.modify(
                customer_id,
                invoice_settings={"default_payment_method": pm},
            )
    at.update(at.TableNames.AGENCIES, agency_id, {"payment_method_on_file": True})
    try:
        ensure_subscription(agency_id)
    except Exception as e:  # noqa: BLE001 — sub creation shouldn't kill the webhook
        logger.warning("billing.subscription_create_failed agency=%s err=%s", agency_id, e)
    logger.info("billing.setup_completed agency=%s", agency_id)


def ensure_subscription(agency_id: str) -> Optional[str]:
    """Get-or-create the agency's £5/unit/month subscription (quantity 0)."""
    if not settings.stripe_price_live_tenancy:
        logger.warning("billing.no_price_configured — set STRIPE_PRICE_LIVE_TENANCY")
        return None
    agency = _agency(agency_id)
    f = agency.get("fields", {})
    if f.get("stripe_subscription_id"):
        return f["stripe_subscription_id"]
    stripe = _stripe()
    customer_id = ensure_customer(agency_id)
    sub = stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": settings.stripe_price_live_tenancy, "quantity": 0}],
        metadata={"agency_id": agency_id},
    )
    at.update(at.TableNames.AGENCIES, agency_id, {
        "stripe_subscription_id": sub["id"],
        "subscription_status": sub.get("status", "active"),
    })
    logger.info("billing.subscription_created agency=%s sub=%s", agency_id, sub["id"])
    return sub["id"]


# ---------------------------------------------------------------------------
# £50 new-tenancy setup fee
# ---------------------------------------------------------------------------
def charge_tenancy_setup_fee(agency_id: str, *, description: str) -> Optional[str]:
    """Charge the one-time £50 fee against the agency's card on file.

    Returns the payments-row id on success, ``None`` when billing is disabled.
    Raises BillingError when there is no payment method or the charge fails.
    """
    if not billing_enabled():
        return None
    agency = _agency(agency_id)
    f = agency.get("fields", {})
    if not f.get("payment_method_on_file"):
        raise BillingError(
            "No payment method on file — add a card in Settings → Billing before "
            "starting a new tenancy.",
            code="payment_method_required",
        )
    stripe = _stripe()
    customer_id = ensure_customer(agency_id)
    amount = settings.stripe_tenancy_setup_fee_pence
    try:
        stripe.InvoiceItem.create(
            customer=customer_id,
            amount=amount,
            currency=settings.stripe_currency,
            description=description,
        )
        invoice = stripe.Invoice.create(
            customer=customer_id,
            collection_method="charge_automatically",
            auto_advance=False,
            description=description,
        )
        invoice = stripe.Invoice.pay(invoice["id"])
    except Exception as e:  # noqa: BLE001
        logger.warning("billing.setup_fee_failed agency=%s err=%s", agency_id, e)
        raise BillingError(f"Card charge for the £50 tenancy fee failed: {e}",
                           code="charge_failed")
    if invoice.get("status") != "paid":
        raise BillingError("The £50 tenancy fee invoice was not paid.", code="charge_failed")

    pay = at.create(at.TableNames.PAYMENTS, {
        "agency_id": agency_id,
        "payment_type": "tenancy_setup_fee",
        "amount": amount / 100.0,
        "currency": settings.stripe_currency,
        "status": "succeeded",
        "description": description,
        "stripe_customer_id": customer_id,
        "stripe_invoice_id": invoice["id"],
    })
    logger.info("billing.setup_fee_charged agency=%s invoice=%s", agency_id, invoice["id"])
    return pay["id"]


# ---------------------------------------------------------------------------
# Live-tenancy quantity sync (£5 / month / live tenancy)
# ---------------------------------------------------------------------------
def count_live_tenancies(agency_id: str) -> int:
    """Live tenancy = TA signed by landlord AND all tenants (pipeline stage 8+)."""
    rows = at.search(
        at.TableNames.PROPERTIES,
        at.and_(
            at.eq("agency_id", agency_id),
            at.eq("TA_LL_Signed", True),
            at.eq("TA_TT_Signed", True),
        ),
        fresh=True,
    )
    return len(rows)


def sync_live_tenancies(agency_id: str) -> Optional[int]:
    """Set the agency's subscription quantity to its live-tenancy count.
    Returns the count, or None when billing/subscription isn't set up."""
    count = count_live_tenancies(agency_id)
    if not billing_enabled():
        return None
    agency = _agency(agency_id)
    sub_id = agency.get("fields", {}).get("stripe_subscription_id")
    if not sub_id:
        return None
    stripe = _stripe()
    try:
        sub = stripe.Subscription.retrieve(sub_id)
        item_id = sub["items"]["data"][0]["id"]
        current_qty = sub["items"]["data"][0].get("quantity")
        if current_qty != count:
            stripe.Subscription.modify(
                sub_id,
                items=[{"id": item_id, "quantity": count}],
                proration_behavior="none",
            )
            logger.info("billing.quantity_synced agency=%s qty=%s->%s", agency_id, current_qty, count)
        at.update(at.TableNames.AGENCIES, agency_id, {"subscription_status": sub.get("status", "active")})
    except Exception as e:  # noqa: BLE001
        logger.warning("billing.quantity_sync_failed agency=%s err=%s", agency_id, e)
        return None
    return count


async def sync_all_agencies() -> int:
    """Daily reconciliation across every agency (scheduler). Returns how many
    agencies were synced."""
    if not billing_enabled():
        return 0
    agencies = at.all_records(at.TableNames.AGENCIES, fresh=True)
    synced = 0
    for a in agencies:
        if not a.get("fields", {}).get("stripe_subscription_id"):
            continue
        scope = at.set_agency_scope(a["id"])
        try:
            if sync_live_tenancies(a["id"]) is not None:
                synced += 1
        finally:
            at.reset_agency_scope(scope)
    return synced


# ---------------------------------------------------------------------------
# Webhook helpers (called from routers/payments.py)
# ---------------------------------------------------------------------------
def agency_by_customer(customer_id: str | None) -> dict | None:
    if not customer_id:
        return None
    return at.find_first(at.TableNames.AGENCIES, at.eq("stripe_customer_id", customer_id))


def apply_subscription_status(customer_id: str | None, status: str) -> bool:
    agency = agency_by_customer(customer_id)
    if not agency:
        return False
    at.update(at.TableNames.AGENCIES, agency["id"], {"subscription_status": status})
    logger.info("billing.subscription_status agency=%s status=%s", agency["id"], status)
    return True


def billing_summary(agency_id: str) -> dict[str, Any]:
    """Shape the Settings → Billing card."""
    f = _agency(agency_id).get("fields", {})
    return {
        "enabled": billing_enabled(),
        "payment_method_on_file": bool(f.get("payment_method_on_file")),
        "subscription_status": f.get("subscription_status") or "none",
        "live_tenancies": count_live_tenancies(agency_id),
        "pricing": {
            "tenancy_setup_fee": settings.stripe_tenancy_setup_fee_pence / 100.0,
            "live_tenancy_monthly": 5.0,
            "currency": settings.stripe_currency,
        },
    }
