"""Stripe payments — checkout sessions + webhook, backed by the ``payments`` table.

Scope (first cut of the supabase-stripe integration):

  GET  /api/properties/{property_id}/payments           List payments for a property
  POST /api/properties/{property_id}/payments/checkout  Create a payment row + Stripe
                                                        Checkout Session, return its URL
  POST /webhook/stripe                                  Stripe webhook → flip payment status

Degrades gracefully: with no ``STRIPE_SECRET_KEY`` configured the checkout
endpoint returns 501 (the rest of the app is unaffected), and the webhook
accepts unsigned events only when no ``STRIPE_WEBHOOK_SECRET`` is set (dev).

Typical flow: agent records an offer → creates a "holding_deposit" checkout →
sends the URL to the tenant → Stripe redirects + fires
``checkout.session.completed`` → the payment row flips to ``succeeded``.
Funds-cleared remains a manual gate flag for now; surfacing succeeded payments
there is a follow-up.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.core.auth import Agent, require_agent
from app.core.logger import get_logger
from app.db import supabase_client as at

router = APIRouter(tags=["payments"])
logger = get_logger(__name__)

PaymentType = Literal["holding_deposit", "deposit", "first_month_rent", "rent", "fee", "other"]


def _stripe():
    """Configured stripe module, or raise 501 when not set up."""
    if not settings.stripe_secret_key:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "Stripe is not configured — set STRIPE_SECRET_KEY (and STRIPE_WEBHOOK_SECRET) in .env.",
        )
    try:
        import stripe  # local import — app must run without the SDK in dev
    except ImportError as e:  # pragma: no cover
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, f"stripe package not installed: {e}")
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _to_summary(rec: dict) -> dict:
    f = rec.get("fields", {})
    return {
        "id": rec["id"],
        "payment_type": f.get("payment_type"),
        "amount": f.get("amount"),
        "currency": f.get("currency"),
        "status": f.get("status"),
        "description": f.get("description"),
        "stripe_checkout_session_id": f.get("stripe_checkout_session_id"),
        "stripe_payment_intent_id": f.get("stripe_payment_intent_id"),
        "created_at": rec.get("createdTime"),
    }


@router.get("/api/properties/{property_id}/payments")
def list_payments(property_id: str, _: Agent = Depends(require_agent)) -> dict[str, Any]:
    try:
        at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    rows = at.search(at.TableNames.PAYMENTS, at.eq("property_id", property_id))
    rows.sort(key=lambda r: r.get("createdTime") or "", reverse=True)
    return {"property_id": property_id, "payments": [_to_summary(r) for r in rows]}


class CheckoutRequest(BaseModel):
    payment_type: PaymentType = "holding_deposit"
    amount: float = Field(..., gt=0, description="Amount in major units (e.g. pounds)")
    description: Optional[str] = None
    payer_email: Optional[EmailStr] = None
    tenant_id: Optional[str] = None
    offer_id: Optional[str] = None


@router.post("/api/properties/{property_id}/payments/checkout", status_code=status.HTTP_201_CREATED)
def create_checkout(
    property_id: str,
    body: CheckoutRequest,
    agent: Agent = Depends(require_agent),
) -> dict[str, Any]:
    try:
        prop = at.get(at.TableNames.PROPERTIES, property_id)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    address = prop.get("fields", {}).get("Address", "")

    stripe = _stripe()

    description = body.description or f"{body.payment_type.replace('_', ' ').title()} — {address}"
    payment = at.create(at.TableNames.PAYMENTS, {
        "property_id": property_id,
        "tenant_id": body.tenant_id,
        "offer_id": body.offer_id,
        "payment_type": body.payment_type,
        "amount": body.amount,
        "currency": settings.stripe_currency,
        "status": "pending",
        "description": description,
        "metadata": {"created_by": agent.email},
    })

    base = settings.frontend_base_url.rstrip("/")
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": settings.stripe_currency,
                    "product_data": {"name": description},
                    "unit_amount": int(round(body.amount * 100)),
                },
                "quantity": 1,
            }],
            customer_email=body.payer_email,
            success_url=f"{base}/properties/{property_id}?payment=success",
            cancel_url=f"{base}/properties/{property_id}?payment=cancelled",
            metadata={"payment_id": payment["id"], "property_id": property_id},
        )
    except Exception as e:  # noqa: BLE001 — surface Stripe errors as 502, keep the row for audit
        at.update(at.TableNames.PAYMENTS, payment["id"], {"status": "failed",
                                                          "description": f"{description} (Stripe error: {e})"})
        logger.error("stripe.checkout_create_failed err=%s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Stripe checkout creation failed: {e}")

    at.update(at.TableNames.PAYMENTS, payment["id"], {
        "stripe_checkout_session_id": session["id"],
        "stripe_payment_intent_id": session.get("payment_intent"),
    })
    logger.info("stripe.checkout_created payment=%s session=%s", payment["id"], session["id"])
    return {
        "payment_id": payment["id"],
        "checkout_url": session["url"],
        "session_id": session["id"],
    }


def _find_payment(session_id: str | None = None, intent_id: str | None = None) -> dict | None:
    if session_id:
        row = at.find_first(at.TableNames.PAYMENTS, at.eq("stripe_checkout_session_id", session_id))
        if row:
            return row
    if intent_id:
        return at.find_first(at.TableNames.PAYMENTS, at.eq("stripe_payment_intent_id", intent_id))
    return None


@router.post("/webhook/stripe")
async def stripe_webhook(
    req: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    raw = await req.body()
    secret = settings.stripe_webhook_secret

    if secret:
        stripe = _stripe()
        try:
            event = stripe.Webhook.construct_event(raw, stripe_signature, secret)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Stripe signature: {e}")
        event = dict(event)
    else:
        # Dev convenience (stripe CLI / manual replays). Log loud.
        logger.warning("Stripe webhook secret not set — accepting unverified event")
        import json
        try:
            event = json.loads(raw)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid JSON: {e}")

    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}

    handled = False
    if etype == "checkout.session.completed":
        payment = _find_payment(session_id=obj.get("id"))
        if payment:
            at.update(at.TableNames.PAYMENTS, payment["id"], {
                "status": "succeeded" if obj.get("payment_status") == "paid" else "processing",
                "stripe_payment_intent_id": obj.get("payment_intent"),
                "stripe_customer_id": obj.get("customer"),
            })
            handled = True
    elif etype == "checkout.session.expired":
        payment = _find_payment(session_id=obj.get("id"))
        if payment:
            at.update(at.TableNames.PAYMENTS, payment["id"], {"status": "cancelled"})
            handled = True
    elif etype == "payment_intent.payment_failed":
        payment = _find_payment(intent_id=obj.get("id"))
        if payment:
            at.update(at.TableNames.PAYMENTS, payment["id"], {"status": "failed"})
            handled = True
    elif etype == "charge.refunded":
        payment = _find_payment(intent_id=obj.get("payment_intent"))
        if payment:
            at.update(at.TableNames.PAYMENTS, payment["id"], {"status": "refunded"})
            handled = True

    logger.info("stripe.webhook type=%s handled=%s", etype, handled)
    return {"received": True, "type": etype, "handled": handled}
