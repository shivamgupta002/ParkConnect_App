"""Notification model — in-app record of a scan/call/report/subscription event."""
from datetime import datetime
from typing import Literal

from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class Notification(Document):
    user: Link[User]
    type: Literal["scan", "call_missed", "call_completed", "report", "subscription"]
    title: str
    message: str
    is_read: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "notifications"
