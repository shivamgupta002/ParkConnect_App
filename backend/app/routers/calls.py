"""
Privacy calling system — the core differentiator of ParkConnect.

Flow:
  1. Scanner (no account, on the public /vehicle/{token} page) POSTs their
     own phone number to /calls/initiate.
  2. We look up the vehicle/owner behind that QR token, create a `calls`
     record, and ask Twilio to dial the SCANNER first (since the scanner is
     on a web page, not already on a call — Twilio needs a number to ring).
  3. When the scanner answers, Twilio requests TwiML from /calls/twiml/{id}.
     We return a <Dial> that bridges them to the OWNER's real number, with
     the caller ID on both legs set to TWILIO_PHONE_NUMBER.
  4. Twilio posts status updates (ringing/in-progress/completed/etc) to
     /calls/status/{id}, which we use to keep the calls doc in sync.

Neither the scanner nor the owner ever sees the other's real number — both
legs of the bridged call show TWILIO_PHONE_NUMBER as caller ID.
"""
from datetime import datetime, timedelta
from typing import Optional

import phonenumbers
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from phonenumbers import NumberParseException
from pydantic import BaseModel, field_validator
from slowapi import Limiter

from app.config import settings
from app.core.deps import get_current_user
from app.core.rate_limit import get_token_from_body
from app.models.call import Call
from app.models.qr_code import QRCode
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services import twilio_service

router = APIRouter(prefix="/calls", tags=["calls"])

# Separate limiter instance keyed by QR token rather than IP — see
# core/rate_limit.py for why. If your app already has a shared `limiter`
# instance created in main.py (the usual slowapi pattern), import and reuse
# that one instead of instantiating a second Limiter here; two separate
# Limiter instances both attached to the same app is harmless but redundant.
token_limiter = Limiter(key_func=get_token_from_body)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class InitiateCallRequest(BaseModel):
    token: str
    scanner_phone: str

    @field_validator("scanner_phone")
    @classmethod
    def validate_e164(cls, v: str) -> str:
        try:
            parsed = phonenumbers.parse(v, None)
        except NumberParseException:
            raise ValueError("scanner_phone must be a valid phone number in E.164 format")
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("scanner_phone must be a valid phone number in E.164 format")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class InitiateCallResponse(BaseModel):
    status: str
    call_id: str


class CallHistoryItem(BaseModel):
    id: str
    vehicle_id: str
    status: str
    duration_seconds: Optional[int]
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redact_phone(phone: str) -> str:
    """
    Redacts all but the last 2 digits of an E.164 phone number, e.g.
    "+919876543210" -> "+91**********10". We never store the scanner's full
    number in plaintext in a document owners/admins can browse — the redacted
    form is enough for context ("someone called about your car") without
    being personally identifying.
    """
    if len(phone) <= 4:
        return "*" * len(phone)
    # Keep the leading "+" and country-code-ish prefix illegible, keep last 2 digits.
    visible_tail = phone[-2:]
    redacted_middle = "*" * (len(phone) - 2 - 1)  # -1 for the leading '+'
    return f"{phone[0]}{redacted_middle}{visible_tail}"


async def _get_active_qr_or_404(token: str) -> QRCode:
    """
    Same generic-404 rule as Phase 4's GET /vehicle/{token}: don't
    distinguish "token doesn't exist" from "token was deactivated" from
    "token expired" — no reason to leak which to an unauthenticated caller.
    """
    qr = await QRCode.find_one(QRCode.token == token)
    is_expired = qr and qr.expires_at and qr.expires_at < datetime.utcnow()
    if qr is None or not qr.is_active or is_expired:
        raise HTTPException(status_code=404, detail="This QR code is no longer active")
    return qr


# ---------------------------------------------------------------------------
# POST /calls/initiate — PUBLIC
# ---------------------------------------------------------------------------

@router.post("/initiate", response_model=InitiateCallResponse)
@token_limiter.limit("3/10minutes")
async def initiate_call(request: Request, payload: InitiateCallRequest):
    qr = await _get_active_qr_or_404(payload.token)

    vehicle = await Vehicle.get(qr.vehicle.ref.id)
    if vehicle is None or not vehicle.is_active:
        raise HTTPException(status_code=404, detail="This QR code is no longer active")

    owner = await User.get(vehicle.owner.ref.id)
    if owner is None:
        raise HTTPException(status_code=404, detail="This QR code is no longer active")

    call_doc = Call(
        vehicle=vehicle,
        owner=owner,
        status="initiating",
        scanner_masked_number=_redact_phone(payload.scanner_phone),
    )
    await call_doc.insert()

    twiml_url = f"{settings.BACKEND_URL}/calls/twiml/{call_doc.id}"
    status_callback_url = f"{settings.BACKEND_URL}/calls/status/{call_doc.id}"

    try:
        call_sid = twilio_service.initiate_call(
            to=payload.scanner_phone,
            twiml_url=twiml_url,
            status_callback_url=status_callback_url,
        )
    except Exception:
        call_doc.status = "failed"
        await call_doc.save()
        raise HTTPException(
            status_code=502,
            detail="Could not place the call right now. Please try again shortly.",
        )

    call_doc.twilio_call_sid = call_sid
    await call_doc.save()

    return InitiateCallResponse(status="calling", call_id=str(call_doc.id))


# ---------------------------------------------------------------------------
# POST /calls/twiml/{call_id} — Twilio webhook
# ---------------------------------------------------------------------------

@router.post("/twiml/{call_id}")
async def call_twiml(call_id: str, request: Request):
    form = await request.form()
    params = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")

    # The URL Twilio signs must be the exact public URL it was configured to
    # call — reconstruct it from settings.BACKEND_URL rather than trusting
    # request.url, since the latter can be altered by a proxy.
    full_url = f"{settings.BACKEND_URL}/calls/twiml/{call_id}"

    if not twilio_service.validate_twilio_signature(full_url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    call_doc = await Call.get(call_id)
    if call_doc is None:
        # Defensive: hang up gracefully rather than 404ing a Twilio webhook.
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say>Sorry, this call could not be connected.</Say><Hangup/></Response>"
        )
        return Response(content=twiml, media_type="application/xml")

    owner = await User.get(call_doc.owner.ref.id)
    owner_phone = getattr(owner, "phone_number", None) if owner else None

    if not owner_phone:
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say>Sorry, the vehicle owner could not be reached right now.</Say>"
            "<Hangup/></Response>"
        )
        return Response(content=twiml, media_type="application/xml")

    # Never log owner_phone. It only ever flows into this TwiML response,
    # which goes straight back to Twilio over a signed, HTTPS webhook.
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Dial callerId="{settings.TWILIO_PHONE_NUMBER}" timeout="30">'
        f"<Number>{owner_phone}</Number>"
        "</Dial></Response>"
    )
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# POST /calls/status/{call_id} — Twilio webhook
# ---------------------------------------------------------------------------

_TERMINAL_STATUSES = {"completed", "no-answer", "failed"}

# Twilio's CallStatus values don't map 1:1 onto our own status enum in every
# case — normalize here so calls.status only ever holds one of the values
# declared on the Call model.
_TWILIO_STATUS_MAP = {
    "queued": "initiating",
    "initiated": "initiating",
    "ringing": "ringing",
    "in-progress": "in-progress",
    "completed": "completed",
    "busy": "no-answer",
    "no-answer": "no-answer",
    "failed": "failed",
    "canceled": "failed",
}


@router.post("/status/{call_id}")
async def call_status(call_id: str, request: Request):
    form = await request.form()
    params = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")

    full_url = f"{settings.BACKEND_URL}/calls/status/{call_id}"

    if not twilio_service.validate_twilio_signature(full_url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    call_doc = await Call.get(call_id)
    if call_doc is None:
        # Nothing to update; still 200 so Twilio doesn't retry indefinitely.
        return {"ok": True}

    twilio_status = params.get("CallStatus", "")
    mapped_status = _TWILIO_STATUS_MAP.get(twilio_status)
    if mapped_status:
        call_doc.status = mapped_status

    duration_raw = params.get("CallDuration")
    if duration_raw is not None:
        try:
            call_doc.duration_seconds = int(duration_raw)
        except ValueError:
            pass

    if call_doc.status in _TERMINAL_STATUSES and call_doc.ended_at is None:
        call_doc.ended_at = datetime.utcnow()
        # TODO: trigger notification (Phase 6) — on "completed", notify the
        # owner their vehicle was scanned and called; on "no-answer" or
        # "failed", notify them they missed a call about their vehicle.
        # Left as a hook for Phase 6's notification_service.notify(); not
        # implemented in this phase per the Phase 5 spec.

    await call_doc.save()
    return {"ok": True}


# ---------------------------------------------------------------------------
# GET /calls — auth required, owner's own call history
# ---------------------------------------------------------------------------

@router.get("", response_model=list[CallHistoryItem])
async def list_calls(
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    calls = (
        await Call.find(Call.owner.id == current_user.id)
        .sort(-Call.created_at)
        .skip(skip)
        .limit(limit)
        .to_list()
    )
    return [
        CallHistoryItem(
            id=str(c.id),
            vehicle_id=str(c.vehicle.ref.id),
            status=c.status,
            duration_seconds=c.duration_seconds,
            created_at=c.created_at,
        )
        for c in calls
    ]