"""
Request/response schemas for QR generation (owner-facing) and the public
scan lookup.

PublicVehicleResponse is intentionally minimal — see the privacy-boundary
comment in app/routers/qr.py. There is no "owner" field, no "vehicle_number"
field, and no internal id field on this model on purpose; do not add one.
"""
from pydantic import BaseModel


class QRCodeResponse(BaseModel):
    token: str
    qr_image_url: str | None = None


class PublicVehicleResponse(BaseModel):
    vehicle_type: str
    brand: str
    model: str
    color: str
    is_active: bool
    