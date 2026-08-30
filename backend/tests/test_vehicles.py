"""
Phase 3 vehicle management tests.

Twilio is mocked (as in test_auth.py) so register+verify can produce a real
access token without sending real SMS. Each test creates its own user(s) via
the actual /auth endpoints rather than inserting User documents directly, so
these tests exercise the real auth->vehicles flow end to end.
"""
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.qr_code import QRCode
from app.models.subscription import Subscription
from app.models.vehicle import Vehicle

VALID_PASSWORD = "Password123"


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


async def _make_premium(email: str) -> None:
    from app.models.user import User

    user = await User.find_one(User.email == email)
    # Link fields must be matched by comparing DBRefs via .to_ref(), not by
    # a dotted "link.id == ..." path -- see app/routers/vehicles.py for the
    # same pattern used in the actual endpoint code.
    sub = await Subscription.find_one(
        Subscription.user == user.to_ref(), fetch_links=False
    )
    sub.plan = "premium"
    await sub.save()


@pytest.mark.asyncio
async def test_free_plan_second_vehicle_rejected():
    async with await _client() as client:
        headers = await _register_and_login(client)

        first = await client.post("/vehicles", json=_vehicle_payload(), headers=headers)
        assert first.status_code == 201

        second = await client.post(
            "/vehicles",
            json=_vehicle_payload(vehicle_number="KA01AB9999"),
            headers=headers,
        )
        assert second.status_code == 403


@pytest.mark.asyncio
async def test_premium_plan_can_add_multiple_vehicles():
    async with await _client() as client:
        headers = await _register_and_login(
            client, email="premium@example.com", phone="+919876543211"
        )
        await _make_premium("premium@example.com")

        first = await client.post("/vehicles", json=_vehicle_payload(), headers=headers)
        assert first.status_code == 201

        second = await client.post(
            "/vehicles",
            json=_vehicle_payload(vehicle_number="KA01AB9999"),
            headers=headers,
        )
        assert second.status_code == 201


@pytest.mark.asyncio
async def test_duplicate_vehicle_number_across_users_rejected():
    async with await _client() as client:
        headers_a = await _register_and_login(
            client, email="usera@example.com", phone="+919876543212"
        )
        headers_b = await _register_and_login(
            client, email="userb@example.com", phone="+919876543213"
        )

        first = await client.post("/vehicles", json=_vehicle_payload(), headers=headers_a)
        assert first.status_code == 201

        second = await client.post("/vehicles", json=_vehicle_payload(), headers=headers_b)
        assert second.status_code == 409


@pytest.mark.asyncio
async def test_cannot_access_or_modify_another_users_vehicle():
    async with await _client() as client:
        headers_a = await _register_and_login(
            client, email="usera2@example.com", phone="+919876543214"
        )
        headers_b = await _register_and_login(
            client, email="userb2@example.com", phone="+919876543215"
        )

        create_resp = await client.post("/vehicles", json=_vehicle_payload(), headers=headers_a)
        vehicle_id = create_resp.json()["id"]

        get_resp = await client.get(f"/vehicles/{vehicle_id}", headers=headers_b)
        assert get_resp.status_code == 404

        put_resp = await client.put(
            f"/vehicles/{vehicle_id}", json={"color": "Black"}, headers=headers_b
        )
        assert put_resp.status_code == 404

        delete_resp = await client.delete(f"/vehicles/{vehicle_id}", headers=headers_b)
        assert delete_resp.status_code == 404

        # Owner themself can still fetch/update it fine.
        own_get = await client.get(f"/vehicles/{vehicle_id}", headers=headers_a)
        assert own_get.status_code == 200


@pytest.mark.asyncio
async def test_delete_soft_deletes_and_deactivates_qr():
    async with await _client() as client:
        headers = await _register_and_login(
            client, email="ownerqr@example.com", phone="+919876543216"
        )

        create_resp = await client.post("/vehicles", json=_vehicle_payload(), headers=headers)
        vehicle_id = create_resp.json()["id"]

        vehicle = await Vehicle.get(vehicle_id)
        qr = QRCode(token="test-token-123", vehicle=vehicle, is_active=True)
        await qr.insert()
        vehicle.qr_code_id = qr
        await vehicle.save()

        delete_resp = await client.delete(f"/vehicles/{vehicle_id}", headers=headers)
        assert delete_resp.status_code == 204

        refreshed_vehicle = await Vehicle.get(vehicle_id)
        assert refreshed_vehicle.is_active is False

        refreshed_qr = await QRCode.get(qr.id)
        assert refreshed_qr.is_active is False


@pytest.mark.asyncio
async def test_malformed_vehicle_id_returns_404_not_500():
    async with await _client() as client:
        headers = await _register_and_login(
            client, email="malformed@example.com", phone="+919876543217"
        )
        resp = await client.get("/vehicles/not-a-valid-objectid", headers=headers)
        assert resp.status_code == 404
