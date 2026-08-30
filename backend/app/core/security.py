"""
Security primitives: password hashing and JWT creation/decoding.

Kept deliberately dependency-light and side-effect-free (no DB calls here) so
it's trivial to unit test and reuse from both the auth router and
core/deps.py's request-time token verification.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- Password hashing ---

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT creation ---

def create_access_token(user_id: str, is_admin: bool = False) -> str:
    """Short-lived token (ACCESS_TOKEN_EXPIRE_MINUTES) used to authenticate
    normal API requests. Carries is_admin so get_current_admin can check it
    without an extra DB round-trip, though deps.py still re-verifies against
    the DB record as the source of truth."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "is_admin": is_admin,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Long-lived token (REFRESH_TOKEN_EXPIRE_DAYS) used only to mint new
    access tokens via POST /auth/refresh. Signed with a DIFFERENT secret than
    access tokens so a leaked access-token secret alone can't be used to
    forge long-lived refresh tokens."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.JWT_REFRESH_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_token(token: str, secret: str) -> Optional[dict]:
    """Decodes and validates a JWT's signature and expiry against the given
    secret. Returns the payload dict on success, or None on any failure
    (expired, malformed, wrong signature) — callers turn that into the
    appropriate HTTP error, this function stays HTTP-agnostic."""
    try:
        return jwt.decode(token, secret, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
