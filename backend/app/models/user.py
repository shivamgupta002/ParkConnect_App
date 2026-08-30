"""User account model."""
from datetime import datetime

import pymongo
from beanie import Document
from pydantic import EmailStr, Field


class User(Document):
    full_name: str
    email: EmailStr
    phone_number: str  # E.164 format, e.g. +919876543210
    hashed_password: str
    is_verified: bool = False
    is_admin: bool = False
    is_premium: bool = False
    is_suspended: bool = False  
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"
        indexes = [
            pymongo.IndexModel("email", unique=True),
            pymongo.IndexModel("phone_number", unique=True),
        ]

    async def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return await super().save(*args, **kwargs)
