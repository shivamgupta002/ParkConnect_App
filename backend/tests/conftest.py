"""
Shared pytest fixtures.

Uses mongomock-motor for an in-memory MongoDB substitute so the test suite
never needs a real MongoDB server running. Beanie is (re)initialized fresh
for every test function against a uniquely-named mock database, so tests
never leak state into one another regardless of execution order.
"""
import uuid

import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.core.rate_limit import limiter
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

ALL_MODELS = [
    User,
    Vehicle,
    QRCode,
    Call,
    Report,
    Notification,
    Subscription,
    Payment,
    AuditLog,
]


@pytest.fixture(autouse=True)
async def init_test_db():
    """
    Fresh in-memory database per test. autouse=True means every test in the
    suite gets an isolated Beanie/Mongo state without needing to remember to
    request this fixture explicitly.

    Also resets the shared slowapi rate limiter's storage between tests —
    otherwise every test shares the same client IP (127.0.0.1) against the
    TestClient, and a rate limit hit in one test would bleed into the next.
    Tests that specifically exercise rate limiting (test_sixth_login_...)
    still work correctly since the limit is exhausted and checked entirely
    within that single test.
    """
    limiter.reset()

    client = AsyncMongoMockClient()
    db_name = f"parkconnect_test_{uuid.uuid4().hex}"
    await init_beanie(database=client[db_name], document_models=ALL_MODELS)
    yield
