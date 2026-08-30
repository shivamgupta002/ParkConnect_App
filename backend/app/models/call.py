"""Call model — one masked-call attempt/session between a scanner and an owner."""

from datetime import datetime
from typing import Literal, Optional

from beanie import Document, Link
from pydantic import Field

from app.models.user import User
from app.models.vehicle import Vehicle


class Call(Document):
    vehicle: Link[Vehicle]
    owner: Link[User]
    twilio_call_sid: Optional[str] = None
    status: Literal[
        "initiating", "ringing", "in-progress", "completed", "no-answer", "failed"
    ] = "initiating"
    duration_seconds: Optional[int] = None
    scanner_masked_number: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None

    class Settings:
        name = "calls"
