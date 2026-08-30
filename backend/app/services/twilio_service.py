"""
Thin wrapper around Twilio's Verify API.

This is the ONLY place that touches the Twilio SDK directly for OTP
send/check — routers call send_otp()/check_otp() so tests can mock this
single module instead of reaching into the Twilio client internals.
"""
import logging

from twilio.rest import Client
from twilio.request_validator import RequestValidator

from app.config import settings

logger = logging.getLogger(__name__)

# Reuse a single Client instance across the module — same pattern as the
# Verify client from Phase 2. Voice calls and OTP both go through Twilio's
# main REST client.
_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

# RequestValidator is used to verify X-Twilio-Signature on inbound webhooks
# (twiml + status callbacks). Kept as a module-level singleton for the same
# reason as _client.
_validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)


def send_otp(phone_number: str) -> None:
    """
    Sends an OTP code to phone_number via Twilio Verify.

    Deliberately returns nothing meaningful (not the verification SID) —
    callers shouldn't need Twilio-specific details, just "it was sent".
    Raises whatever exception the Twilio SDK raises on failure; callers
    decide how to handle that (Phase 2 routers let it propagate as a 500,
    since a failed OTP send during registration/forgot-password is a genuine
    server-side problem the user can't route around).
    """
    _client.verify.v2.services(settings.TWILIO_VERIFY_SERVICE_SID).verifications.create(
        to=phone_number, channel="sms"
    )
    logger.info("OTP send requested for phone ending in %s", phone_number[-4:])


def check_otp(phone_number: str, code: str) -> bool:
    """
    Checks a submitted OTP code against Twilio Verify.

    Returns True only if Twilio reports the check as "approved". Any other
    status (or a Twilio error, e.g. no pending verification for this number)
    is treated as an invalid code — callers should show a generic "invalid or
    expired code" message rather than distinguishing the failure reason, to
    avoid leaking whether the phone number itself is registered.
    """
    check = _client.verify.v2.services(
        settings.TWILIO_VERIFY_SERVICE_SID
    ).verification_checks.create(to=phone_number, code=code)
    return check.status == "approved"

def initiate_call(to: str, twiml_url: str, status_callback_url: str) -> str:
    """
    Places an outbound call to `to` (the scanner's phone). When answered,
    Twilio requests TwiML from `twiml_url`, which is where we bridge to the
    owner's real number. Status updates are posted to `status_callback_url`.
 
    Returns the Twilio Call SID.
    """
    call = _client.calls.create(
        to=to,
        from_=settings.TWILIO_PHONE_NUMBER,
        url=twiml_url,
        status_callback=status_callback_url,
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )
    return call.sid
 
 
def validate_twilio_signature(url: str, params: dict, signature: str) -> bool:
    """
    Verifies that an inbound webhook request genuinely came from Twilio,
    using the X-Twilio-Signature header. `url` must be the exact, full
    public URL Twilio was configured to call (including scheme/host/path),
    and `params` the form-encoded POST body Twilio sent.
    """
    return _validator.validate(url, params, signature)
