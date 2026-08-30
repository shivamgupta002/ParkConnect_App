"""
Audit log model — records admin actions.

Not one of the original 8 collections from the spec, but required by the
Security Design section's "audit log of admin actions" requirement. Written
to by the admin panel (Phase 8) and by user-suspension actions.
"""
from datetime import datetime

from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class AuditLog(Document):
    admin_user: Link[User]
    action: str
    target_type: str
    target_id: str
    meta: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "audit_logs"
