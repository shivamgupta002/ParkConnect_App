"""
Phase 4 QR code tests.

Cloudinary's upload call is mocked (same reasoning as mocking Twilio in
test_auth.py/test_vehicles.py: no real network call, no real credentials
needed, deterministic output) so these tests exercise the real
auth -> vehicle -> QR flow end to end without touching an external service.
"""
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.qr_code import QRCode
from app.models.vehicle import Vehicle

VALID_PASSWORD = "Password123"
FAKE_SECURE_URL = "https://res.cloudinary.com/testcloud/image/upload/v1/fake_qr.png"


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _vehicle_payload(**overrides):
    payload = {
        "vehicle_type": "car",
        "vehicle_number": "KA01AB1234",
        "brand": "Toyota",
        "model": "Innova",
        "color": "White",
        "emergency_contact": "+919876500000",
    }
    payload.update(overrides)
    return payload


async def _register_and_login(client, email="owner1@example.com", phone="+919876543210"):
    """Registers + verifies a new user via the real endpoints and returns an
    Authorization header dict with a valid access token."""
    with patch("app.routers.auth.twilio_service.send_otp"), patch(
        "app.routers.auth.twilio_service.check_otp"
    ) as mock_check:
        mock_check.return_value = True

        await client.post(
            "/auth/register",
            json={
                "full_name": "Test Owner",
                "email": email,
                "phone_number": phone,
                "password": VALID_PASSWORD,
            },
        )
        verify_resp = await client.post(
            "/auth/verify-otp",
            json={"phone_number": phone, "code": "123456"},
        )
        token = verify_resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}


def _mock_cloudinary_upload():
    """Patches the single seam qr_service uses to talk to Cloudinary."""
    return patch(
        "app.services.qr_service.upload_qr_image",
        return_value=FAKE_SECURE_URL,
    )


@pytest.mark.asyncio
async def test_generate_qr_creates_active_qr_and_deactivates_prior_one():
    async with await _client() as client:
        headers = await _register_and_login(client, email="qrgen@example.com", phone="+919876543220")

        create_resp = await client.post("/vehicles", json=_vehicle_payload(), headers=headers)
        vehicle_id = create_resp.json()["id"]

        with _mock_cloudinary_upload():
            first_qr_resp = await client.post(f"/vehicles/{vehicle_id}/qr", headers=headers)
        assert first_qr_resp.status_code == 201
        first_body = first_qr_resp.json()
        assert first_body["token"]
        assert first_body["qr_image_url"] == FAKE_SECURE_URL

        first_qr = await QRCode.find_one(QRCode.token == first_body["token"])
        assert first_qr is not None
        assert first_qr.is_active is True

        with _mock_cloudinary_upload():
            second_qr_resp = await client.post(f"/vehicles/{vehicle_id}/qr", headers=headers)
        assert second_qr_resp.status_code == 201
        second_body = second_qr_resp.json()
        assert second_body["token"] != first_body["token"]

        # Prior QR deactivated, not deleted.
        refreshed_first_qr = await QRCode.get(first_qr.id)
        assert refreshed_first_qr is not None
        assert refreshed_first_qr.is_active is False

        second_qr = await QRCode.find_one(QRCode.token == second_body["token"])
        assert second_qr.is_active is True

        # Vehicle now points at the new QR.
        vehicle = await Vehicle.get(vehicle_id, fetch_links=False)
        assert vehicle.qr_code_id.ref.id == second_qr.id


@pytest.mark.asyncio
async def test_generate_qr_requires_ownership():
    async with await _client() as client:
        headers_a = await _register_and_login(client, email="qrowner@example.com", phone="+919876543221")
        headers_b = await _register_and_login(client, email="qrother@example.com", phone="+919876543222")

        create_resp = await client.post("/vehicles", json=_vehicle_payload(), headers=headers_a)
        vehicle_id = create_resp.json()["id"]

        resp = await client.post(f"/vehicles/{vehicle_id}/qr", headers=headers_b)
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_scan_active_token_returns_only_safe_fields():
    async with await _client() as client:
        headers = await _register_and_login(client, email="scanner1@example.com", phone="+919876543223")

        create_resp = await client.post("/vehicles", json=_vehicle_payload(), headers=headers)
        vehicle_id = create_resp.json()["id"]

        with _mock_cloudinary_upload():
            qr_resp = await client.post(f"/vehicles/{vehicle_id}/qr", headers=headers)
        token = qr_resp.json()["token"]

        scan_resp = await client.get(f"/vehicle/{token}")
        assert scan_resp.status_code == 200

        body = scan_resp.json()
        assert body == {
            "vehicle_type": "car",
            "brand": "Toyota",
            "model": "Innova",
            "color": "White",
            "is_active": True,
        }

        raw_text = scan_resp.text.lower()
        for forbidden in ("owner", "email", "phone", "vehicle_number", "emergency_contact"):
            assert forbidden not in raw_text


@pytest.mark.asyncio
async def test_scan_deactivated_or_nonexistent_token_returns_generic_404():
    async with await _client() as client:
        headers = await _register_and_login(client, email="scanner2@example.com", phone="+919876543224")

        create_resp = await client.post("/vehicles", json=_vehicle_payload(), headers=headers)
        vehicle_id = create_resp.json()["id"]

        with _mock_cloudinary_upload():
            qr_resp = await client.post(f"/vehicles/{vehicle_id}/qr", headers=headers)
        token = qr_resp.json()["token"]

        # Deactivate the vehicle -> cascades to deactivating its QR (Phase 3
        # DELETE /vehicles/{id} behavior).
        await client.delete(f"/vehicles/{vehicle_id}", headers=headers)

        deactivated_resp = await client.get(f"/vehicle/{token}")
        nonexistent_resp = await client.get("/vehicle/this-token-was-never-issued")

        assert deactivated_resp.status_code == 404
        assert nonexistent_resp.status_code == 404
        assert deactivated_resp.json()["detail"] == nonexistent_resp.json()["detail"]


@pytest.mark.asyncio
async def test_scan_count_increments_on_each_successful_scan():
    async with await _client() as client:
        headers = await _register_and_login(client, email="scanner3@example.com", phone="+919876543225")

        create_resp = await client.post("/vehicles", json=_vehicle_payload(), headers=headers)
        vehicle_id = create_resp.json()["id"]

        with _mock_cloudinary_upload():
            qr_resp = await client.post(f"/vehicles/{vehicle_id}/qr", headers=headers)
        token = qr_resp.json()["token"]

        for expected_count in (1, 2, 3):
            await client.get(f"/vehicle/{token}")
            qr = await QRCode.find_one(QRCode.token == token)
            assert qr.scan_count == expected_count
            