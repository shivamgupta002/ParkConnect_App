"""
Subscription and payment endpoints.

Two route groups live in this file:
  - /subscriptions/*  (authenticated — the owner-facing plan info + upgrade trigger)
  - /payments/webhook (PUBLIC — Razorpay calls this server-to-server, it can't send a JWT)

Activation flow, deliberately asynchronous:
  1. POST /subscriptions/upgrade creates a Razorpay Order + a "created" Payment doc,
     and returns just enough for the frontend to open Razorpay Checkout. The
     subscription is NOT touched here.
  2. The user pays in Razorpay's widget.
  3. Razorpay calls POST /payments/webhook with a payment.captured event once the
     payment actually clears. ONLY this handler marks the Payment "paid" and
     activates the Subscription. This is what makes the flow trustworthy — a user
     can't just call /subscriptions/upgrade and claim they paid; only Razorpay's
     signed webhook can flip the plan.
"""
import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import settings
from app.core.deps import get_current_user
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.subscription import SubscriptionResponse, UpgradeOrderResponse
from app.services import razorpay_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

# Separate router for the webhook since it's mounted at /payments, not
# /subscriptions, and is public (no get_current_user dependency at all).
payments_router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/me", response_model=SubscriptionResponse)
async def get_my_subscription(current_user: User = Depends(get_current_user)):
    # Lazy expiry check first, so a stale "premium" row never leaks out to
    # the caller even if no scheduled job has run yet — see
    # razorpay_service.check_and_downgrade_expired_subscriptions for why this
    # is a lazy per-request check rather than a batch job.
    await razorpay_service.check_and_downgrade_expired_subscriptions(current_user)

    subscription = await Subscription.find_one(
        Subscription.user == current_user.to_ref(), fetch_links=False
    )

    if subscription is None:
        # A user should always have a subscription doc (created at
        # registration in Phase 2), but default to a free-plan view rather
        # than 500ing if one is somehow missing.
        return SubscriptionResponse(
            plan="free",
            status="active",
            start_date=current_user.created_at,
            end_date=None,
        )

    return SubscriptionResponse(
        plan=subscription.plan,
        status=subscription.status,
        start_date=subscription.start_date,
        end_date=subscription.end_date,
    )


@router.post("/upgrade", response_model=UpgradeOrderResponse)
async def upgrade_subscription(current_user: User = Depends(get_current_user)):
    amount_paise = settings.PREMIUM_MONTHLY_PRICE_PAISE

    order = razorpay_service.create_order(
        amount_paise=amount_paise,
        currency="INR",
        receipt=f"user:{current_user.id}",
    )

    subscription = await Subscription.find_one(
        Subscription.user == current_user.to_ref(), fetch_links=False
    )
    if subscription is None:
        # Defensive fallback — should already exist from registration, but
        # a Payment doc needs *some* Subscription to link against.
        subscription = Subscription(user=current_user.to_ref(), plan="free", status="active")
        await subscription.save()

    payment = Payment(
        user=current_user.to_ref(),
        subscription=subscription.to_ref(),
        amount=amount_paise / 100,  # store rupees on the Payment doc for human-readable reporting
        currency="INR",
        provider="razorpay",
        provider_order_id=order["id"],
        status="created",
    )
    await payment.save()

    return UpgradeOrderResponse(
        order_id=order["id"],
        amount=amount_paise,
        currency="INR",
        razorpay_key_id=settings.RAZORPAY_KEY_ID,
    )


@payments_router.post("/webhook", status_code=status.HTTP_200_OK)
async def razorpay_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not razorpay_service.verify_webhook_signature(raw_body, signature):
        logger.warning("Rejected Razorpay webhook: invalid signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )

    payload = await request.json()
    event = payload.get("event")

    if event != "payment.captured":
        # Razorpay sends many event types (order.paid, payment.failed, etc).
        # We only act on payment.captured for the MVP; everything else is
        # acknowledged with 200 so Razorpay doesn't retry it forever, but
        # otherwise ignored.
        return {"status": "ignored", "event": event}

    payment_entity = payload["payload"]["payment"]["entity"]
    provider_order_id = payment_entity.get("order_id")
    provider_payment_id = payment_entity.get("id")

    payment = await Payment.find_one(
        Payment.provider_order_id == provider_order_id, fetch_links=False
    )
    if payment is None:
        # A payment.captured event for an order we have no record of —
        # acknowledge with 200 (nothing to retry) but log loudly, this
        # shouldn't happen outside of manual Razorpay dashboard testing.
        logger.warning(
            "Received payment.captured for unknown order_id=%s", provider_order_id
        )
        return {"status": "ignored", "reason": "unknown order_id"}

    # Idempotency: Razorpay may redeliver the same webhook. If we've already
    # marked this payment paid, don't re-activate/re-extend the subscription.
    if payment.status == "paid":
        return {"status": "already_processed"}

    payment.status = "paid"
    payment.provider_payment_id = provider_payment_id
    await payment.save()

    user = await User.get(payment.user.ref.id)
    if user is not None:
        await razorpay_service.activate_premium_subscription(user)

    return {"status": "ok"}