"""
ParkConnect backend entrypoint.

Phase 0: app wiring, CORS, DB init on startup, GET /health.
Phase 2: auth router mounted, slowapi rate limiting wired in globally.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.core.rate_limit import limiter
from app.database import init_db
from app.routers import auth, vehicles, qr

from app.routers import calls  # add alongside your other router imports
from app.routers import notifications
from app.routers import reports
from app.routers import admin
from app.routers import subscriptions

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown: nothing to clean up yet (Motor's client closes with the process).


app = FastAPI(
    title="ParkConnect API",
    description="Privacy-based vehicle owner contact system.",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Rate limiting (slowapi) ---
# app.state.limiter + the exception handler + SlowAPIMiddleware together are
# what actually make @limiter.limit(...) decorators on individual routes
# return 429 responses instead of silently no-op'ing.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS origins are read from config so production can add the real frontend
# domain later without a code change (see Settings.cors_origins).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(vehicles.router)
app.include_router(qr.vehicle_qr_router)
app.include_router(qr.public_scan_router)
app.include_router(calls.router)
app.include_router(notifications.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(subscriptions.router)
app.include_router(subscriptions.payments_router)

@app.get("/health")
async def health_check():
    """Basic liveness check, also used by the frontend to prove the two
    servers are wired together during Phase 0."""
    return {"status": "ok"}

