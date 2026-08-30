"""
Notification delivery for ParkConnect.

Single entry point: notify(user, type, title, message, channels=[...]).

Design rules (do not violate these when editing):
- ALWAYS create a `notifications` document, regardless of whether any channel
  actually delivers successfully. The in-app notification list must never be
  empty just because SendGrid/Twilio/FCM had a bad day.
- EACH channel is wrapped in its own try/except. One channel failing must
  never block another channel or bubble up to the caller (a request handler).
- Failures are logged with logging.warning including channel + user id only.
  NEVER log the message body — it may reference call/report details we don't
  want sitting in plaintext application logs.
"""

import logging
from typing import Iterable, Literal

from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioRestException

from app.config import settings
from app.models.user import User
from app.models.notification import Notification

logger = logging.getLogger(__name__)

NotificationType = Literal[
    "scan", "call_missed", "call_completed", "report", "subscription"
]
Channel = Literal["push", "sms", "email"]

DEFAULT_CHANNELS: tuple[Channel, ...] = ("push", "sms", "email")

# Reuse a single Twilio client for SMS (same account as OTP/calls, different
# capability). If your twilio_service.py already exposes a shared client,
# import and reuse that instead of constructing a second one here.
_twilio_client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


async def notify(
    user: User,
    type: NotificationType,
    title: str,
    message: str,
    channels: Iterable[Channel] = DEFAULT_CHANNELS,
) -> Notification:
    """
    Create the in-app notification record, then best-effort deliver on each
    requested channel. Never raises — safe to call from a request handler
    directly or via BackgroundTasks.
    """
    notification = Notification(
        user=user,
        type=type,
        title=title,
        message=message,
        is_read=False,
    )
    await notification.insert()

    channel_set = set(channels)

    if "sms" in channel_set:
        try:
            send_sms(user.phone_number, f"{title}: {message}")
        except Exception:
            logger.warning(
                "notification_service: sms delivery failed for user_id=%s",
                str(user.id),
            )

    if "email" in channel_set:
        try:
            send_email(user.email, title, message)
        except Exception:
            logger.warning(
                "notification_service: email delivery failed for user_id=%s",
                str(user.id),
            )

    if "push" in channel_set:
        try:
            send_push(user, title, message)
        except Exception:
            logger.warning(
                "notification_service: push delivery failed for user_id=%s",
                str(user.id),
            )

    return notification


def send_sms(phone: str, message: str) -> None:
    """Send an SMS via Twilio. Raises on failure — caller catches it."""
    _twilio_client.messages.create(
        to=phone,
        from_=settings.TWILIO_PHONE_NUMBER,
        body=message,
    )


def send_email(email: str, subject: str, message: str) -> None:
    """
    Send an email via SendGrid.

    Choice: SendGrid over raw SMTP, since it's already in the env var list
    from the build guide (SENDGRID_API_KEY) and needs no mail server ops.
    If you'd rather use SMTP, swap this function's body for smtplib and
    drop the sendgrid import — notify() doesn't care which you use.
    """
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    if not settings.SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY not configured")

    mail = Mail(
        from_email=settings.SENDGRID_FROM_EMAIL,
        to_emails=email,
        subject=subject,
        plain_text_content=message,
    )
    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    sg.send(mail)


def send_push(user: User, title: str, message: str) -> None:
    """
    Send a push notification via Firebase Cloud Messaging.

    Push is optional for v1 (per the build guide) — if the user has no
    registered FCM device token, skip silently rather than raising, since
    "no token yet" is an expected state, not a delivery failure.

    Assumes a `fcm_token: Optional[str]` field on the User model. If you
    haven't added that field yet, add it now (small migration-style addition,
    default None) — same pattern as is_suspended in Phase 8.
    """
    fcm_token = getattr(user, "fcm_token", None)
    if not fcm_token:
        return  # no device registered — not an error, just nothing to do

    if not settings.FIREBASE_CREDENTIALS_JSON:
        raise RuntimeError("FIREBASE_CREDENTIALS_JSON not configured")

    import firebase_admin
    from firebase_admin import credentials, messaging

    if not firebase_admin._apps:
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_JSON)
        firebase_admin.initialize_app(cred)

    messaging.send(
        messaging.Message(
            notification=messaging.Notification(title=title, body=message),
            token=fcm_token,
        )
    )