"""
QR code endpoints.

Two distinct routers live in this file because they sit at two different,
deliberately-separate URL shapes:

  - `vehicle_qr_router`, mounted under /vehicles (plural, authenticated) —
    POST /vehicles/{id}/qr, owner-only, generates/regenerates a QR code.
  - `public_scan_router`, mounted at the bare root (singular /vehicle/...,
    unauthenticated) — GET /vehicle/{token}, the anonymous lookup a scanner's
    browser hits after scanning a sticker.

Keeping them as separate router objects (rather than one router with a mixed
prefix) makes the auth boundary between "owner action" and "public lookup"
visible at a glance in main.py, instead of buried in per-route Depends().
"""
from datetime import datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.qr_code import QRCode
from app.schemas.qr import PublicVehicleResponse, QRCodeResponse
from app.services.qr_service import issue_qr_for_vehicle

vehicle_qr_router = APIRouter(prefix="/vehicles", tags=["qr"])
public_scan_router = APIRouter(tags=["public-scan"])


@vehicle_qr_router.post(
    "/{vehicle_id}/qr",
    response_model=QRCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_vehicle_qr(
    vehicle_id: str,
    current_user: User = Depends(get_current_user),
):
    """Returns the vehicle's one QR code — creating it on first call, or
    simply returning the existing one on every call after that (same
    token/image, whether it's currently active or dormant/expired). See
    qr_service.issue_qr_for_vehicle: a vehicle never gets a second token."""
    try:
        oid = PydanticObjectId(vehicle_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    vehicle = await Vehicle.get(oid, fetch_links=False)
    if vehicle is None or vehicle.owner.ref.id != current_user.id:
        # Same "don't distinguish missing vs. not-yours" rule as the Phase 3
        # vehicle routes.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    qr = await issue_qr_for_vehicle(vehicle)

    return QRCodeResponse(token=qr.token, qr_image_url=qr.qr_image_url)


@public_scan_router.get("/vehicle/{token}", response_model=PublicVehicleResponse)
@limiter.limit("30/minute")
async def scan_vehicle(request: Request, token: str):
    """
    PUBLIC, unauthenticated lookup — this is the page a stranger's phone
    hits after scanning a physical QR sticker.

    Privacy boundary (deliberate, not an oversight): the response below
    includes ONLY vehicle_type, brand, model, color, and is_active. It never
    includes owner name/email/phone, the vehicle_number/plate, or any
    internal document id beyond the token itself. A scanner's whole job here
    is "identify the car, then call/report" — nothing about the owner's
    identity is needed for that, and this endpoint has no auth on it, so
    anything added here is exposed to the entire internet. Do not "fix" this
    by adding owner fields back in.

    Not-found, deactivated, and expired all return the exact same generic
    404 — distinguishing them would let someone probe which tokens ever
    existed vs. were merely deactivated.
    """
    not_active = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="This QR code is no longer active.",
    )

    # fetch_links=False + a manual Vehicle.get() below rather than
    # fetch_links=True: Beanie resolves fetch_links via an aggregation
    # $lookup with a `pipeline` stage, which mongomock (used by the test
    # suite) doesn't implement. Two simple queries against real MongoDB are
    # just as cheap and side-step that gap entirely.
    qr = await QRCode.find_one(QRCode.token == token, fetch_links=False)
    if qr is None:
        raise not_active

    if not qr.is_active:
        raise not_active

    if qr.expires_at is not None and qr.expires_at < datetime.utcnow():
        raise not_active

    vehicle = await Vehicle.get(qr.vehicle.ref.id)
    if vehicle is None:
        # Defensive: a dangling link looks the same to the scanner as any
        # other unavailable QR code.
        raise not_active

    qr.scan_count += 1
    await qr.save()

    return PublicVehicleResponse(
        vehicle_type=vehicle.vehicle_type,
        brand=vehicle.brand,
        model=vehicle.model,
        color=vehicle.color,
        is_active=vehicle.is_active,
    )
