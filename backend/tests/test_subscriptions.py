"""
Phase 9 subscription/payment tests.

The Razorpay SDK is mocked entirely — no real network calls. Following the
same pattern as test_auth.py/test_vehicles.py, we patch
app.routers.subscriptions.razorpay_service (the point of use inside the
router), not the razorpay module itself, so the router's own call sites are
what's actually exercised.
"""
import hashlib
import hmac
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.models.user import User

VALID_PASSWORD = "Password123"


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _register_and_login(client, email="owner1@example.com", phone="+919876543210"):
    """Same helper as test_vehicles.py: registers + verifies a new user via
    the real endpoints and returns an Authorization header dict."""
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


def _fake_order(order_id="order_fake123", amount=19900):
    return {"id": order_id, "amount": amount, "currency": "INR", "status": "created"}


def _captured_webhook_payload(order_id, payment_id="pay_fake123"):
    return {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "status": "captured",
                }
            }
        },
    }


@pytest.mark.asyncio
async def test_upgrade_creates_payment_and_returns_order_id():
    async with await _client() as client:
        headers = await _register_and_login(client)

        with patch(
            "app.routers.subscriptions.razorpay_service.create_order"
        ) as mock_create_order:
            mock_create_order.return_value = _fake_order()

            resp = await client.post("/subscriptions/upgrade", headers=headers)
            assert resp.status_code == 200
            body = resp.json()
            assert body["order_id"] == "order_fake123"
            assert body["amount"] == 19900
            assert "razorpay_key_id" in body

        payment = await Payment.find_one(Payment.provider_order_id == "order_fake123")
        assert payment is not None
        assert payment.status == "created"


@pytest.mark.asyncio
async def test_valid_signed_webhook_activates_premium():
    async with await _client() as client:
        headers = await _register_and_login(client)

        with patch(
            "app.routers.subscriptions.razorpay_service.create_order"
        ) as mock_create_order:
            mock_create_order.return_value = _fake_order(order_id="order_abc")
            await client.post("/subscriptions/upgrade", headers=headers)

        payload = _captured_webhook_payload(order_id="order_abc")

        with patch(
            "app.routers.subscriptions.razorpay_service.verify_webhook_signature"
        ) as mock_verify:
            mock_verify.return_value = True

            resp = await client.post(
                "/payments/webhook",
                json=payload,
                headers={"X-Razorpay-Signature": "valid-sig"},
            )
            assert resp.status_code == 200

        user = await User.find_one(User.email == "owner1@example.com")
        subscription = await Subscription.find_one(
            Subscription.user == user.to_ref(), fetch_links=False
        )
        assert subscription.plan == "premium"
        assert subscription.status == "active"
        assert subscription.end_date is not None
        assert subscription.end_date > datetime.utcnow() + timedelta(days=29)

        payment = await Payment.find_one(Payment.provider_order_id == "order_abc")
        assert payment.status == "paid"
        assert payment.provider_payment_id == "pay_fake123"


@pytest.mark.asyncio
async def test_invalid_signature_rejected_and_subscription_unchanged():
    async with await _client() as client:
        headers = await _register_and_login(client)

        with patch(
            "app.routers.subscriptions.razorpay_service.create_order"
        ) as mock_create_order:
            mock_create_order.return_value = _fake_order(order_id="order_bad_sig")
            await client.post("/subscriptions/upgrade", headers=headers)

        payload = _captured_webhook_payload(order_id="order_bad_sig")

        with patch(
            "app.routers.subscriptions.razorpay_service.verify_webhook_signature"
        ) as mock_verify:
            mock_verify.return_value = False

            resp = await client.post(
                "/payments/webhook",
                json=payload,
                headers={"X-Razorpay-Signature": "tampered-sig"},
            )
            assert resp.status_code == 400

        user = await User.find_one(User.email == "owner1@example.com")
        subscription = await Subscription.find_one(
            Subscription.user == user.to_ref(), fetch_links=False
        )
        assert subscription.plan == "free"

        payment = await Payment.find_one(Payment.provider_order_id == "order_bad_sig")
        assert payment.status == "created"


@pytest.mark.asyncio
async def test_replayed_webhook_does_not_double_extend():
    async with await _client() as client:
        headers = await _register_and_login(client)

        with patch(
            "app.routers.subscriptions.razorpay_service.create_order"
        ) as mock_create_order:
            mock_create_order.return_value = _fake_order(order_id="order_replay")
            await client.post("/subscriptions/upgrade", headers=headers)

        payload = _captured_webhook_payload(order_id="order_replay")

        with patch(
            "app.routers.subscriptions.razorpay_service.verify_webhook_signature"
        ) as mock_verify:
            mock_verify.return_value = True

            first = await client.post(
                "/payments/webhook",
                json=payload,
                headers={"X-Razorpay-Signature": "valid-sig"},
            )
            assert first.status_code == 200

            user = await User.find_one(User.email == "owner1@example.com")
            sub_after_first = await Subscription.find_one(
                Subscription.user == user.to_ref(), fetch_links=False
            )
            end_date_after_first = sub_after_first.end_date

            second = await client.post(
                "/payments/webhook",
                json=payload,
                headers={"X-Razorpay-Signature": "valid-sig"},
            )
            assert second.status_code == 200
            assert second.json()["status"] == "already_processed"

        sub_after_second = await Subscription.find_one(
            Subscription.user == user.to_ref(), fetch_links=False
        )
        assert sub_after_second.end_date == end_date_after_first


@pytest.mark.asyncio
async def test_expired_premium_subscription_auto_downgrades_on_me():
    async with await _client() as client:
        headers = await _register_and_login(client)

        user = await User.find_one(User.email == "owner1@example.com")
        subscription = await Subscription.find_one(
            Subscription.user == user.to_ref(), fetch_links=False
        )
        subscription.plan = "premium"
        subscription.status = "active"
        subscription.end_date = datetime.utcnow() - timedelta(days=1)  # already expired
        await subscription.save()

        resp = await client.get("/subscriptions/me", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan"] == "free"
        assert body["status"] == "expired"

        refreshed = await Subscription.find_one(
            Subscription.user == user.to_ref(), fetch_links=False
        )
        assert refreshed.plan == "free"
        assert refreshed.status == "expired"