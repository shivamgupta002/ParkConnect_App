"""Report model — public complaint/emergency report against a vehicle."""
from datetime import datetime
from typing import Literal, Optional

from beanie import Document, Link
from pydantic import Field

from app.models.vehicle import Vehicle


class Report(Document):
    vehicle: Link[Vehicle]
    report_type: Literal["wrong_parking", "lights_on", "accident", "emergency", "other"]
    message: str
    reporter_contact: Optional[str] = None
    status: Literal["open", "reviewed", "resolved"] = "open"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "reports"
