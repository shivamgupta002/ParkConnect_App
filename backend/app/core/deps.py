"""
FastAPI auth dependencies.

get_current_user reads the Authorization: Bearer <token> header, decodes and
validates it, and loads the corresponding User from Mongo — this is the
single source of truth every protected route depends on. get_current_admin
builds on top of it and additionally requires is_admin=True.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.core.security import decode_token
from app.models.user import User

# auto_error=False so we can raise our own consistent 401 message instead of
# FastAPI's default "Not authenticated" for a missing header.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or not credentials.credentials:
        raise unauthorized

    payload = decode_token(credentials.credentials, settings.JWT_SECRET_KEY)
    if payload is None or payload.get("type") != "access":
        raise unauthorized

    user_id = payload.get("sub")
    if not user_id:
        raise unauthorized

    user = await User.get(user_id)
    if user is None:
        raise unauthorized

    if user.is_suspended:
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended",
        )

    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
