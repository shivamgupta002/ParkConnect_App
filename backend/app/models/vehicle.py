"""Vehicle model — owned by a User, optionally linked to an active QRCode."""
from datetime import datetime
from typing import Literal, Optional

import pymongo
from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class Vehicle(Document):
    owner: Link[User]
    vehicle_type: Literal["car", "bike"]
    vehicle_number: str
    brand: str
    model: str
    color: str
    emergency_contact: str
    qr_code_id: Optional[Link["QRCode"]] = None  # forward ref, resolved below
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "vehicles"
        indexes = [
            pymongo.IndexModel("vehicle_number", unique=True),
        ]

    async def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return await super().save(*args, **kwargs)


# Resolve the forward reference to QRCode without a circular import at module
# load time: qr_code.py imports Vehicle directly, so Vehicle can't import
# QRCode back at the top of this file. Beanie/Pydantic rebuild the model once
# QRCode is defined (see models/__init__.py import order).
from app.models.qr_code import QRCode  # noqa: E402

Vehicle.model_rebuild()
