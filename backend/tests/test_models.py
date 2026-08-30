"""
Phase 1 test: creates one document of each of the 9 collections with valid
data, saves it, fetches it back by id, and asserts the fields round-trip.

Uses mongomock-motor (in-memory MongoDB substitute) rather than a real local
MongoDB server — see tests/conftest.py for the fixture that wires this up
fresh for every test.

Note: mongomock's aggregation engine doesn't support the $lookup pipeline
operator Beanie's `fetch_links=True` relies on, so linked documents are
resolved individually via `link_field.fetch()` instead — this also happens
to match how Beanie links are used for real in the routers (lazy resolution,
not eager joins), so it's a reasonable pattern either way.
"""
from datetime import datetime, timedelta

import pytest

from app.models import (
    User,
    Vehicle,
    QRCode,
    Call,
    Report,
    Notification,
    Subscription,
    Payment,
    AuditLog,
)


@pytest.mark.asyncio
async def test_user_roundtrip():
    user = User(
        full_name="Asha Rao",
        email="asha@example.com",
        phone_number="+919876543210",
        hashed_password="not-a-real-hash",
    )
    await user.insert()

    fetched = await User.get(user.id)
    assert fetched is not None
    assert fetched.full_name == "Asha Rao"
    assert fetched.email == "asha@example.com"
    assert fetched.phone_number == "+919876543210"
    assert fetched.is_verified is False
    assert fetched.is_admin is False
    assert fetched.is_premium is False
    assert fetched.is_suspended is False
    assert isinstance(fetched.created_at, datetime)
    assert isinstance(fetched.updated_at, datetime)


@pytest.mark.asyncio
async def test_vehicle_roundtrip():
    owner = User(
        full_name="Vikram Singh",
        email="vikram@example.com",
        phone_number="+919876500001",
        hashed_password="hash",
    )
    await owner.insert()

    vehicle = Vehicle(
        owner=owner,
        vehicle_type="car",
        vehicle_number="DL01AB1234",
        brand="Maruti",
        model="Swift",
        color="Red",
        emergency_contact="+919876500002",
    )
    await vehicle.insert()

    fetched = await Vehicle.get(vehicle.id)
    assert fetched is not None
    assert fetched.vehicle_type == "car"
    assert fetched.vehicle_number == "DL01AB1234"
    assert fetched.brand == "Maruti"
    assert fetched.is_active is True

    fetched_owner = await fetched.owner.fetch()
    assert fetched_owner.email == "vikram@example.com"


@pytest.mark.asyncio
async def test_qr_code_roundtrip():
    owner = User(
        full_name="Neha Gupta",
        email="neha@example.com",
        phone_number="+919876500003",
        hashed_password="hash",
    )
    await owner.insert()

    vehicle = Vehicle(
        owner=owner,
        vehicle_type="bike",
        vehicle_number="DL01AB5678",
        brand="Honda",
        model="Activa",
        color="Black",
        emergency_contact="+919876500004",
    )
    await vehicle.insert()

    qr = QRCode(token="abc123token", vehicle=vehicle)
    await qr.insert()

    fetched = await QRCode.get(qr.id)
    assert fetched is not None
    assert fetched.token == "abc123token"
    assert fetched.is_active is True
    assert fetched.scan_count == 0

    fetched_vehicle = await fetched.vehicle.fetch()
    assert fetched_vehicle.vehicle_number == "DL01AB5678"


@pytest.mark.asyncio
async def test_call_roundtrip():
    owner = User(
        full_name="Ravi Kumar",
        email="ravi@example.com",
        phone_number="+919876500005",
        hashed_password="hash",
    )
    await owner.insert()

    vehicle = Vehicle(
        owner=owner,
        vehicle_type="car",
        vehicle_number="DL01AB9999",
        brand="Hyundai",
        model="i20",
        color="White",
        emergency_contact="+919876500006",
    )
    await vehicle.insert()

    call = Call(
        vehicle=vehicle,
        owner=owner,
        twilio_call_sid="CA1234567890",
        status="initiating",
        scanner_masked_number="+91******89",
    )
    await call.insert()

    fetched = await Call.get(call.id)
    assert fetched is not None
    assert fetched.status == "initiating"
    assert fetched.twilio_call_sid == "CA1234567890"
    assert fetched.scanner_masked_number == "+91******89"

    fetched_owner = await fetched.owner.fetch()
    assert fetched_owner.email == "ravi@example.com"


@pytest.mark.asyncio
async def test_report_roundtrip():
    owner = User(
        full_name="Priya Nair",
        email="priya@example.com",
        phone_number="+919876500007",
        hashed_password="hash",
    )
    await owner.insert()

    vehicle = Vehicle(
        owner=owner,
        vehicle_type="car",
        vehicle_number="DL01AB1111",
        brand="Tata",
        model="Nexon",
        color="Blue",
        emergency_contact="+919876500008",
    )
    await vehicle.insert()

    report = Report(
        vehicle=vehicle,
        report_type="wrong_parking",
        message="Blocking the driveway",
    )
    await report.insert()

    fetched = await Report.get(report.id)
    assert fetched is not None
    assert fetched.report_type == "wrong_parking"
    assert fetched.status == "open"

    fetched_vehicle = await fetched.vehicle.fetch()
    assert fetched_vehicle.vehicle_number == "DL01AB1111"


@pytest.mark.asyncio
async def test_notification_roundtrip():
    user = User(
        full_name="Sameer Joshi",
        email="sameer@example.com",
        phone_number="+919876500009",
        hashed_password="hash",
    )
    await user.insert()

    notification = Notification(
        user=user,
        type="scan",
        title="Your vehicle was scanned",
        message="Someone scanned your QR code just now.",
    )
    await notification.insert()

    fetched = await Notification.get(notification.id)
    assert fetched is not None
    assert fetched.type == "scan"
    assert fetched.is_read is False

    fetched_user = await fetched.user.fetch()
    assert fetched_user.email == "sameer@example.com"


@pytest.mark.asyncio
async def test_subscription_roundtrip():
    user = User(
        full_name="Kavya Iyer",
        email="kavya@example.com",
        phone_number="+919876500010",
        hashed_password="hash",
    )
    await user.insert()

    subscription = Subscription(user=user)
    await subscription.insert()

    fetched = await Subscription.get(subscription.id)
    assert fetched is not None
    assert fetched.plan == "free"
    assert fetched.status == "active"

    fetched_user = await fetched.user.fetch()
    assert fetched_user.email == "kavya@example.com"


@pytest.mark.asyncio
async def test_payment_roundtrip():
    user = User(
        full_name="Arjun Mehta",
        email="arjun@example.com",
        phone_number="+919876500011",
        hashed_password="hash",
    )
    await user.insert()

    subscription = Subscription(user=user, plan="premium")
    await subscription.insert()

    payment = Payment(
        user=user,
        subscription=subscription,
        amount=299.0,
        provider_order_id="order_abc123",
    )
    await payment.insert()

    fetched = await Payment.get(payment.id)
    assert fetched is not None
    assert fetched.amount == 299.0
    assert fetched.currency == "INR"
    assert fetched.provider == "razorpay"
    assert fetched.status == "created"

    fetched_user = await fetched.user.fetch()
    assert fetched_user.email == "arjun@example.com"
    fetched_subscription = await fetched.subscription.fetch()
    assert fetched_subscription.plan == "premium"


@pytest.mark.asyncio
async def test_audit_log_roundtrip():
    admin = User(
        full_name="Admin User",
        email="admin@example.com",
        phone_number="+919876500012",
        hashed_password="hash",
        is_admin=True,
    )
    await admin.insert()

    log = AuditLog(
        admin_user=admin,
        action="update_report_status",
        target_type="report",
        target_id="some-report-id",
        meta={"new_status": "resolved"},
    )
    await log.insert()

    fetched = await AuditLog.get(log.id)
    assert fetched is not None
    assert fetched.action == "update_report_status"
    assert fetched.target_type == "report"
    assert fetched.meta == {"new_status": "resolved"}

    fetched_admin = await fetched.admin_user.fetch()
    assert fetched_admin.email == "admin@example.com"
