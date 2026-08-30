"""Subscription model — a user's current plan (free/premium)."""
from datetime import datetime
from typing import Literal, Optional

from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class Subscription(Document):
    user: Link[User]
    plan: Literal["free", "premium"] = "free"
    status: Literal["active", "expired", "cancelled"] = "active"
    start_date: datetime = Field(default_factory=datetime.utcnow)
    end_date: Optional[datetime] = None

    class Settings:
        name = "subscriptions"
