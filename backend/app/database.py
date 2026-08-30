"""
MongoDB connection setup (Motor async client) and Beanie ODM initialization.

Phase 0 intentionally registers zero Document models — Phase 1 will populate
`document_models=[...]` with all 9 collections. Keeping the model list empty
here (rather than skipping init_beanie entirely) means the startup wiring is
already correct and future phases only need to add imports, not touch this
connection logic.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from app.config import settings
from app.models import (
    User,
    Vehicle,
    QRCode,
    Call,
    Report,
    Notification,
    Subscription,
    Payment,
    AuditLog,
)

logger = logging.getLogger(__name__)

# Shared Motor client, created once at import time and reused for the life of
# the process (Motor manages its own internal connection pool).
client: AsyncIOMotorClient = AsyncIOMotorClient(settings.MONGODB_URI)


async def init_db() -> None:
    """
    Initialize Beanie against the configured database.

    Called from the FastAPI lifespan on startup. The database name is taken
    from the MONGODB_URI itself (Motor parses it out of the connection string),
    falling back to a sane default if the URI has no path segment.
    """
    database = client.get_default_database(default="parkconnect")

    await init_beanie(
        database=database,
        document_models=[
            User,
            Vehicle,
            QRCode,
            Call,
            Report,
            Notification,
            Subscription,
            Payment,
            AuditLog,
        ],
    )

    logger.info("Beanie initialized against database: %s", database.name)
