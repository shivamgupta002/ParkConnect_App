"""
Phase 2 auth tests.

twilio_service is mocked throughout (patched at the point of use, in
app.routers.auth) so no real SMS is ever sent during tests. send_otp is
mocked as a no-op; check_otp's return value is controlled per-test to
simulate correct/incorrect OTP codes without a real Twilio round-trip.
"""
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

VALID_PASSWORD = "Password123"


def _register_payload(**overrides):
    payload = {
        "full_name": "Test User",
        "email": "testuser@example.com",
        "phone_number": "+919876543210",
        "password": VALID_PASSWORD,
    }
    payload.update(overrides)
    return payload


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_register_verify_login_happy_path():
    with patch("app.routers.auth.twilio_service.send_otp") as mock_send, patch(
        "app.routers.auth.twilio_service.check_otp"
    ) as mock_check:
        mock_send.return_value = None
        mock_check.return_value = True

        async with await _client() as client:
            # Register
            register_resp = await client.post("/auth/register", json=_register_payload())
            assert register_resp.status_code == 200
            mock_send.assert_called_once()

            # Verify OTP
            verify_resp = await client.post(
                "/auth/verify-otp",
                json={"phone_number": "+919876543210", "code": "123456"},
            )
            assert verify_resp.status_code == 200
            verify_body = verify_resp.json()
            assert "access_token" in verify_body
            assert "refresh_token" in verify_body

            # Login
            login_resp = await client.post(
                "/auth/login",
                json={"email": "testuser@example.com", "password": VALID_PASSWORD},
            )
            assert login_resp.status_code == 200
            login_body = login_resp.json()
            assert "access_token" in login_body
            assert "refresh_token" in login_body


@pytest.mark.asyncio
async def test_wrong_otp_code_is_rejected():
    with patch("app.routers.auth.twilio_service.send_otp") as mock_send, patch(
        "app.routers.auth.twilio_service.check_otp"
    ) as mock_check:
        mock_send.return_value = None
        mock_check.return_value = False  # simulate Twilio rejecting the code

        async with await _client() as client:
            await client.post("/auth/register", json=_register_payload())

            verify_resp = await client.post(
                "/auth/verify-otp",
                json={"phone_number": "+919876543210", "code": "000000"},
            )
            assert verify_resp.status_code == 400
            assert "invalid or expired" in verify_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_before_verification_is_rejected():
    with patch("app.routers.auth.twilio_service.send_otp") as mock_send:
        mock_send.return_value = None

        async with await _client() as client:
            await client.post("/auth/register", json=_register_payload())

            # Never verify — attempt to log in directly.
            login_resp = await client.post(
                "/auth/login",
                json={"email": "testuser@example.com", "password": VALID_PASSWORD},
            )
            assert login_resp.status_code == 403
            assert "verify" in login_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_sixth_login_attempt_is_rate_limited():
    with patch("app.routers.auth.twilio_service.send_otp") as mock_send:
        mock_send.return_value = None

        async with await _client() as client:
            await client.post("/auth/register", json=_register_payload())

            # 5 attempts allowed per 5 minutes; all use wrong password so we
            # don't need to verify the account first, we're only testing the
            # rate limiter kicking in on the 6th call.
            bad_login = {"email": "testuser@example.com", "password": "WrongPass123"}

            statuses = []
            for _ in range(6):
                resp = await client.post("/auth/login", json=bad_login)
                statuses.append(resp.status_code)

            # First 5 should NOT be 429 (they're 401 for wrong password);
            # the 6th must be 429.
            assert statuses[:5].count(429) == 0
            assert statuses[5] == 429


@pytest.mark.asyncio
async def test_duplicate_email_registration_returns_409():
    with patch("app.routers.auth.twilio_service.send_otp") as mock_send:
        mock_send.return_value = None

        async with await _client() as client:
            first = await client.post("/auth/register", json=_register_payload())
            assert first.status_code == 200

            second = await client.post(
                "/auth/register",
                json=_register_payload(phone_number="+919876500099"),
            )
            assert second.status_code == 409


@pytest.mark.asyncio
async def test_refresh_token_issues_new_access_token():
    with patch("app.routers.auth.twilio_service.send_otp") as mock_send, patch(
        "app.routers.auth.twilio_service.check_otp"
    ) as mock_check:
        mock_send.return_value = None
        mock_check.return_value = True

        async with await _client() as client:
            await client.post("/auth/register", json=_register_payload())
            verify_resp = await client.post(
                "/auth/verify-otp",
                json={"phone_number": "+919876543210", "code": "123456"},
            )
            refresh_token = verify_resp.json()["refresh_token"]

            refresh_resp = await client.post(
                "/auth/refresh", json={"refresh_token": refresh_token}
            )
            assert refresh_resp.status_code == 200
            assert "access_token" in refresh_resp.json()


@pytest.mark.asyncio
async def test_refresh_with_invalid_token_returns_401():
    async with await _client() as client:
        resp = await client.post(
            "/auth/refresh", json={"refresh_token": "not-a-real-token"}
        )
        assert resp.status_code == 401
