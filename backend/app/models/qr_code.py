"""QR code model — maps a public token to a vehicle."""
from datetime import datetime
from typing import Optional

import pymongo
from beanie import Document, Link
from pydantic import Field

from app.models.vehicle import Vehicle


# class QRCode(Document):
#     token: str  # secrets.token_urlsafe(24), public-facing identifier
#     vehicle: Link[Vehicle]
#     qr_image_url: Optional[str] = None
#     is_active: bool = True
#     scan_count: int = 0
#     expires_at: Optional[datetime] = None
#     created_at: datetime = Field(default_factory=datetime.utcnow)

#     class Settings:
#         name = "qr_codes"
#         indexes = [
#             pymongo.IndexModel("token", unique=True),
#         ]

class QRCode(Document):
    token: str  # secrets.token_urlsafe(24), public-facing identifier
    vehicle: Link[Vehicle]
    qr_image_url: Optional[str] = None
    is_active: bool = True
    scan_count: int = 0
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "qr_codes"
        indexes = [
            pymongo.IndexModel("token", unique=True),
            # Defense-in-depth: enforces "at most one active QR per vehicle"
            # at the database level, on top of the application-level
            # deactivate-then-create logic in qr_service.issue_qr_for_vehicle.
            # Partial index (only applies where is_active == True) so
            # deactivated/historical QR docs for the same vehicle don't
            # collide with each other or with the current active one.
            pymongo.IndexModel(
                "vehicle.$id",
                unique=True,
                partialFilterExpression={"is_active": True},
                name="uniq_active_qr_per_vehicle",
            ),
        ]
