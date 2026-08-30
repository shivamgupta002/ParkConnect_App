"""
Tests for backend/app/routers/calls.py.

The Twilio client is mocked entirely — no real calls are placed during tests.
Adjust the fixture imports (client, db setup, factory helpers for
User/Vehicle/QRCode) to match whatever conftest.py fixtures your Phase 1-4
tests already established; the bodies below assume:

  - `client`: an httpx.AsyncClient / TestClient wired to the FastAPI app
    with a clean test database per test (per your Phase 1 test setup notes).
  - `make_user`, `make_vehicle`, `make_qr`: async factory fixtures that
    create+save a User / Vehicle / QRCode with sensible defaults, returning
    the saved document. If your Phase 1-4 tests use different factory
    names, rename the calls below accordingly.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.call import Call


# ---------------------------------------------------------------------------
# POST /calls/initiate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_initiate_call_creates_doc_and_calls_twilio(client, make_user, make_vehicle, make_qr):
    owner = await make_user(phone_number="+919999999999")
    vehicle = await make_vehicle(owner=owner)
    qr = await make_qr(vehicle=vehicle, is_active=True)

    with patch("app.services.twilio_service._client") as mock_client:
        mock_call = MagicMock()
        mock_call.sid = "CA_test_sid_123"
        mock_client.calls.create.return_value = mock_call

        resp = await client.post(
            "/calls/initiate",
            json={"token": qr.token, "scanner_phone": "+918888888888"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "calling"
    assert "call_id" in body

    call_doc = await Call.get(body["call_id"])
    assert call_doc is not None
    assert call_doc.twilio_call_sid == "CA_test_sid_123"
    assert call_doc.scanner_masked_number != "+918888888888"  # must be redacted
    assert call_doc.scanner_masked_number.endswith("88")

    create_kwargs = mock_client.calls.create.call_args.kwargs
    assert create_kwargs["to"] == "+918888888888"
    assert "url" in create_kwargs and str(call_doc.id) in create_kwargs["url"]


@pytest.mark.asyncio
async def test_initiate_call_rate_limited_per_token(client, make_user, make_vehicle, make_qr):
    owner = await make_user(phone_number="+919999999999")
    vehicle = await make_vehicle(owner=owner)
    qr = await make_qr(vehicle=vehicle, is_active=True)

    with patch("app.services.twilio_service._client") as mock_client:
        mock_call = MagicMock()
        mock_call.sid = "CA_test_sid"
        mock_client.calls.create.return_value = mock_call

        for _ in range(3):
            resp = await client.post(
                "/calls/initiate",
                json={"token": qr.token, "scanner_phone": "+918888888888"},
            )
            assert resp.status_code == 200

        fourth = await client.post(
            "/calls/initiate",
            json={"token": qr.token, "scanner_phone": "+918888888888"},
        )

    assert fourth.status_code == 429


@pytest.mark.asyncio
async def test_initiate_call_invalid_token_returns_generic_404(client):
    resp = await client.post(
        "/calls/initiate",
        json={"token": "nonexistent-token", "scanner_phone": "+918888888888"},
    )
    assert resp.status_code == 404
    assert "no longer active" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /calls/twiml/{call_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_twiml_rejects_missing_or_invalid_signature(client, make_user, make_vehicle):
    owner = await make_user(phone_number="+919999999999")
    vehicle = await make_vehicle(owner=owner)
    call_doc = Call(vehicle=vehicle, owner=owner, status="initiating")
    await call_doc.insert()

    with patch("app.services.twilio_service.validate_twilio_signature", return_value=False):
        resp = await client.post(
            f"/calls/twiml/{call_doc.id}",
            data={"CallSid": "CA_test"},
            headers={"X-Twilio-Signature": "bogus"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_twiml_valid_signature_returns_dial_to_owner(client, make_user, make_vehicle):
    owner = await make_user(phone_number="+919999999999")
    vehicle = await make_vehicle(owner=owner)
    call_doc = Call(vehicle=vehicle, owner=owner, status="ringing")
    await call_doc.insert()

    with patch("app.services.twilio_service.validate_twilio_signature", return_value=True):
        resp = await client.post(
            f"/calls/twiml/{call_doc.id}",
            data={"CallSid": "CA_test"},
            headers={"X-Twilio-Signature": "valid-sig"},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    body = resp.text
    assert "<Dial" in body
    assert owner.phone_number in body
    assert 'callerId="' in body
    from app.config import settings
    assert settings.TWILIO_PHONE_NUMBER in body
    # The scanner's number must never appear in TwiML sent back to Twilio.
    assert "+918888888888" not in body


# ---------------------------------------------------------------------------
# POST /calls/status/{call_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_webhook_updates_status_and_duration(client, make_user, make_vehicle):
    owner = await make_user(phone_number="+919999999999")
    vehicle = await make_vehicle(owner=owner)
    call_doc = Call(vehicle=vehicle, owner=owner, status="in-progress")
    await call_doc.insert()

    with patch("app.services.twilio_service.validate_twilio_signature", return_value=True):
        resp = await client.post(
            f"/calls/status/{call_doc.id}",
            data={"CallStatus": "completed", "CallDuration": "47"},
            headers={"X-Twilio-Signature": "valid-sig"},
        )

    assert resp.status_code == 200
    updated = await Call.get(call_doc.id)
    assert updated.status == "completed"
    assert updated.duration_seconds == 47
    assert updated.ended_at is not None


# ---------------------------------------------------------------------------
# GET /calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_calls_returns_only_own_calls(client, make_user, make_vehicle, auth_headers_for):
    owner = await make_user(phone_number="+919999999999")
    other_owner = await make_user(phone_number="+917777777777")
    vehicle = await make_vehicle(owner=owner)
    other_vehicle = await make_vehicle(owner=other_owner)

    await Call(vehicle=vehicle, owner=owner, status="completed").insert()
    await Call(vehicle=other_vehicle, owner=other_owner, status="completed").insert()

    headers = await auth_headers_for(owner)
    resp = await client.get("/calls", headers=headers)

    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["vehicle_id"] == str(vehicle.id)