"""
Request/response schemas for the /vehicles/* endpoints.

owner is deliberately absent from every request schema — it is always derived
from get_current_user in the router, never accepted from the client, so there
is no way for a caller to create or claim a vehicle on someone else's behalf.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, field_validator


class VehicleCreateRequest(BaseModel):
    vehicle_type: Literal["car", "bike"]
    vehicle_number: str
    brand: str
    model: str
    color: str
    emergency_contact: str

    @field_validator("vehicle_number", "brand", "model", "color", "emergency_contact")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("This field cannot be empty")
        return v.strip()

    @field_validator("vehicle_number")
    @classmethod
    def normalize_vehicle_number(cls, v: str) -> str:
        # Uppercase + strip so "ka01ab1234" and "KA01AB1234" are treated as
        # the same plate for the uniqueness check.
        return v.strip().upper()


class VehicleUpdateRequest(BaseModel):
    # vehicle_number is intentionally NOT updatable here — treated as
    # immutable after creation. The QR code resolves via its own token, not
    # the vehicle_number, so leaving vehicle_number out of this schema is a
    # safety choice about data hygiene/history, not a technical requirement
    # of the QR flow.
    vehicle_type: Optional[Literal["car", "bike"]] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    emergency_contact: Optional[str] = None

    @field_validator("brand", "model", "color", "emergency_contact")
    @classmethod
    def not_blank_if_present(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("This field cannot be empty")
        return v.strip() if v is not None else v


class VehicleResponse(BaseModel):
    id: str
    vehicle_type: str
    vehicle_number: str
    brand: str
    model: str
    color: str
    emergency_contact: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class VehicleListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    vehicles: list[VehicleResponse]
