### handles PNG generation, Cloudinary upload, and the "deactivate old QR → create new one → link to vehicle" workflow.
"""
QR code generation and issuance.

Two responsibilities live here rather than in the router:
  1. Rendering a token into a PNG and uploading it to Cloudinary (the parts
     that talk to an external SDK, so tests can mock this module cleanly).
  2. issue_qr_for_vehicle(): the actual "create a new QR, deactivate the old
     one, link it to the vehicle" workflow, so the router stays thin and this
     logic is reusable/testable on its own.
"""
import io
import secrets
from datetime import datetime, timedelta

import cloudinary
import cloudinary.uploader
import qrcode

from app.config import settings
from app.models.qr_code import QRCode
from app.models.subscription import Subscription
from app.models.vehicle import Vehicle

# Free-plan QR codes are only valid for this many days after issuance; after
# that, GET /vehicle/{token} in routers/qr.py starts 404-ing it (same
# generic "no longer active" response as a deactivated/nonexistent token).
# Premium-plan QR codes never expire (expires_at stays None).
FREE_PLAN_QR_VALIDITY_DAYS = 30

# cloudinary.config() reads CLOUDINARY_URL from the environment automatically,
# but we pass it explicitly from settings so the app fails at startup (via
# Settings validation) rather than silently no-op-ing an upload later if the
# env var is missing.

# cloudinary.config(cloudinary_url=settings.CLOUDINARY_URL) 
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
)



def generate_qr_png_bytes(data: str) -> bytes:
    """Renders `data` (the public scan URL) into a PNG and returns raw bytes."""
    img = qrcode.make(data)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def upload_qr_image(png_bytes: bytes, public_id: str) -> str:
    """Uploads PNG bytes to Cloudinary and returns the secure_url."""
    result = cloudinary.uploader.upload(
        io.BytesIO(png_bytes),
        public_id=public_id,
        folder="parkconnect/qr_codes",
        overwrite=True,
        resource_type="image",
    )
    return result["secure_url"]


async def issue_qr_for_vehicle(vehicle: Vehicle) -> QRCode:
    """
    Returns the vehicle's one-and-only QRCode, creating it if this is the
    vehicle's very first QR. A vehicle NEVER gets a second token: if it
    already has a QR document (active or dormant/expired), that same
    document is returned as-is — this function does not touch its
    is_active/expires_at state. Reactivating a dormant free-plan QR after
    payment is handled separately by
    razorpay_service.reactivate_qr_codes_for_user(), and lapsing one back to
    dormant on non-payment by razorpay_service.deactivate_qr_codes_for_user()
    — both flip is_active/expires_at on THIS SAME document, never create a
    new one. Callers that want to force a brand-new token (there currently
    are none) should not use this function.

    Returns the QRCode document (already saved, with qr_image_url populated
    and vehicle.qr_code_id pointed at it).
    """
    if vehicle.qr_code_id is not None:
        existing = await QRCode.get(vehicle.qr_code_id.ref.id)
        if existing is not None:
            return existing

    token = secrets.token_urlsafe(24)

    expires_at = None
    owner_id = vehicle.owner.ref.id
    subscription = await Subscription.find_one(
        Subscription.user.id == owner_id, fetch_links=False
    )
    if subscription is None or subscription.plan != "premium":
        # Free plan (or no subscription doc at all, defensively treated as
        # free): the QR sticker is only good for FREE_PLAN_QR_VALIDITY_DAYS
        # from today. If the owner doesn't upgrade before then, the QR goes
        # dormant (is_active flipped False by
        # razorpay_service.check_and_downgrade_expired_subscriptions or the
        # lazy check on GET /vehicle/{token}) — NOT deleted, NOT replaced.
        # Paying reactivates this exact same token later. Premium leaves
        # expires_at as None (never expires).
        expires_at = datetime.utcnow() + timedelta(days=FREE_PLAN_QR_VALIDITY_DAYS)

    qr = QRCode(token=token, vehicle=vehicle, is_active=True, expires_at=expires_at)
    await qr.insert()

    scan_url = f"{settings.FRONTEND_URL}/vehicle/{token}"
    png_bytes = generate_qr_png_bytes(scan_url)
    qr.qr_image_url = upload_qr_image(png_bytes, public_id=str(qr.id))
    await qr.save()

    vehicle.qr_code_id = qr
    await vehicle.save()

    return qr