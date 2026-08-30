"""
Thin wrapper around the Razorpay SDK.

Same pattern as app/services/twilio_service.py: this is the ONLY place that
touches the razorpay SDK directly, so routers and tests interact with plain
functions instead of the SDK's client internals — makes the whole payment
flow mockable in tests without a real Razorpay account.
"""
import hmac
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

import razorpay

from app.config import settings
from app.models.payment import Payment
from app.models.qr_code import QRCode
from app.models.subscription import Subscription
from app.models.user import User
from app.models.vehicle import Vehicle

logger = logging.getLogger(__name__)

# Reused module-level client — same singleton pattern as twilio_service's
# _client, so tests mock this one object rather than patching per-call.
_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_order(amount_paise: int, currency: str = "INR", receipt: Optional[str] = None) -> dict:
    """
    Creates a Razorpay Order for `amount_paise` (smallest currency unit —
    paise, not rupees). Returns the raw Razorpay order dict, which includes
    at minimum an "id" field (the provider_order_id we store on the Payment
    doc) and "amount"/"currency" echoed back.

    Raises whatever the Razorpay SDK raises on failure (e.g. bad credentials,
    network error) — callers let it propagate as a 500, same convention as
    twilio_service.send_otp for a genuine server-side failure.
    """
    order = _client.order.create(
        {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "payment_capture": 1,  # auto-capture — we don't do a manual capture step for an MVP
        }
    )
    logger.info("Razorpay order created: %s", order.get("id"))
    return order


def verify_webhook_signature(payload_body: bytes, signature: str) -> bool:
    """
    Verifies an inbound Razorpay webhook's X-Razorpay-Signature header
    against RAZORPAY_WEBHOOK_SECRET.

    Uses the SDK's own verifier (HMAC-SHA256 of the raw request body against
    the webhook secret) rather than hand-rolling HMAC comparison, so this
    stays correct if Razorpay ever changes the signing details.

    Returns True only on a valid, matching signature. Any exception from the
    SDK (malformed signature, wrong type, etc.) is treated as invalid rather
    than propagating — a webhook endpoint must never 500 on a bad signature,
    it must cleanly reject with 400.
    """
    try:
        _client.utility.verify_webhook_signature(
            payload_body.decode("utf-8") if isinstance(payload_body, bytes) else payload_body,
            signature,
            settings.RAZORPAY_WEBHOOK_SECRET,
        )
        return True
    except razorpay.errors.SignatureVerificationError:
        return False
    except Exception:
        # Defensive catch-all: any other unexpected failure while verifying
        # a signature we don't yet trust is still "reject", not "crash".
        logger.warning("Unexpected error verifying Razorpay webhook signature")
        return False


async def activate_premium_subscription(user: User) -> Subscription:
    """
    Flips (or creates) `user`'s subscription to an active 30-day premium
    plan. Called only from the payment.captured webhook handler, never
    directly from POST /subscriptions/upgrade — activation must only happen
    after Razorpay confirms the payment, not when the order is merely
    created (see routers/subscriptions.py).
    """
    now = datetime.utcnow()
    subscription = await Subscription.find_one(
        Subscription.user == user.to_ref(), fetch_links=False
    )

    if subscription is None:
        subscription = Subscription(
            user=user.to_ref(),
            plan="premium",
            status="active",
            start_date=now,
            end_date=now + timedelta(days=30),
        )
    else:
        subscription.plan = "premium"
        subscription.status = "active"
        subscription.start_date = now
        subscription.end_date = now + timedelta(days=30)

    await subscription.save()
    logger.info("Subscription activated as premium for user %s until %s", user.id, subscription.end_date)

    # Payment confirmed. One QR per vehicle, forever — a lapsed free-plan QR
    # is dormant (is_active=False), never destroyed, so paying always just
    # reactivates the SAME sticker instead of forcing a reprint.
    await reactivate_qr_codes_for_user(user)

    return subscription


async def reactivate_qr_codes_for_user(user: User) -> None:
    """
    Called after a user becomes premium (real payment or admin renewal).

    For every QR code belonging to `user`'s vehicles (there is at most one
    QR per vehicle by design — see the uniq_active_qr_per_vehicle index on
    QRCode): flip is_active back to True and clear expires_at. Premium QR
    codes never expire, so this both un-deactivates a dormant free-plan QR
    that had lapsed AND makes it permanent going forward. No new token is
    ever issued here — the vehicle keeps the exact same QR/sticker it
    always had.
    """
    vehicles = await Vehicle.find(Vehicle.owner.id == user.id, fetch_links=False).to_list()
    vehicle_ids = [v.id for v in vehicles]
    if not vehicle_ids:
        return

    await QRCode.find(QRCode.vehicle.id.in_(vehicle_ids)).update(
        {"$set": {"is_active": True, "expires_at": None}}
    )
    logger.info("Reactivated QR code(s) for user %s (%s vehicle(s))", user.id, len(vehicle_ids))


async def deactivate_qr_codes_for_user(user: User) -> None:
    """
    Called when a premium subscription lapses back to free (payment not
    renewed) — see check_and_downgrade_expired_subscriptions below.

    Sets is_active=False on every QR code belonging to `user`'s vehicles.
    The QR/token itself is left untouched (never deleted, never
    regenerated) — it simply stops resolving via GET /vehicle/{token} until
    the user pays again, at which point reactivate_qr_codes_for_user() flips
    it straight back on. This is "dormant", not "permanently dead": the
    same physical sticker keeps working across as many pay/lapse cycles as
    the user goes through.
    """
    vehicles = await Vehicle.find(Vehicle.owner.id == user.id, fetch_links=False).to_list()
    vehicle_ids = [v.id for v in vehicles]
    if not vehicle_ids:
        return

    await QRCode.find(QRCode.vehicle.id.in_(vehicle_ids)).update(
        {"$set": {"is_active": False}}
    )
    logger.info("Deactivated QR code(s) for user %s (subscription lapsed)", user.id)


async def check_and_downgrade_expired_subscriptions(user: User) -> None:
    """
    Lazy expiry check for a single user: if their subscription is premium/
    active but end_date has passed, downgrade to free/expired in place.

    Called at the top of GET /subscriptions/me and GET /vehicles for the
    CURRENT user only — this is deliberately not a batch job. It only
    catches expiry for users who happen to make a request while expired,
    which is fine for an MVP's traffic but should be replaced by a real
    scheduled job (Celery beat, or a simple daily cron script iterating all
    premium/active subscriptions) once there's enough traffic that a user
    might not touch the app again for weeks after expiring — until then
    their plan would silently stay "premium" in the DB despite being past
    end_date.
    """
    subscription = await Subscription.find_one(
        Subscription.user == user.to_ref(), fetch_links=False
    )
    if subscription is None:
        return

    if (
        subscription.plan == "premium"
        and subscription.status == "active"
        and subscription.end_date is not None
        and subscription.end_date < datetime.utcnow()
    ):
        subscription.plan = "free"
        subscription.status = "expired"
        await subscription.save()
        logger.info("Subscription auto-downgraded to free for user %s (expired)", user.id)
        await deactivate_qr_codes_for_user(user)

        