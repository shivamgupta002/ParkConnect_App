"""
Authentication endpoints, mounted at /auth.

Business rules worth calling out (see individual endpoints for detail):
- Registration/login error messages never distinguish "email doesn't exist"
  from "wrong password" (login), nor "phone not registered" from "wrong OTP
  code" (verify-otp), nor whether an email matched at all (forgot-password) —
  this avoids leaking which accounts exist to a prober.
- Duplicate email/phone on register IS reported explicitly, since that's a
  normal signup UX case, not an auth-probing vector — we check for that
  ourselves in Mongo before ever calling Twilio.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import settings
from app.core import security
from app.core.rate_limit import limiter
from app.models.subscription import Subscription
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyOtpRequest,
)
from app.services import twilio_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=MessageResponse)
@limiter.limit("5/5minutes")
async def register(request: Request, body: RegisterRequest):
    existing_email = await User.find_one(User.email == body.email)
    if existing_email is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    existing_phone = await User.find_one(User.phone_number == body.phone_number)
    if existing_phone is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this phone number already exists",
        )

    is_admin_email = body.email.lower() in settings.admin_emails_list

    user = User(
        full_name=body.full_name,
        email=body.email,
        phone_number=body.phone_number,
        hashed_password=security.hash_password(body.password),
        is_verified=False,
        is_admin=is_admin_email,
    )
    await user.insert()

    # Default free-plan subscription, created alongside the account so every
    # user always has exactly one subscription document from day one.
    subscription = Subscription(user=user, plan="free", status="active")
    await subscription.insert()

    twilio_service.send_otp(body.phone_number)

    return MessageResponse(
        message="Registration successful. Please verify your phone number with the code we sent."
    )


@router.post("/verify-otp", response_model=TokenResponse)
@limiter.limit("5/5minutes")
async def verify_otp(request: Request, body: VerifyOtpRequest):
    invalid_code = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired code",
    )

    user = await User.find_one(User.phone_number == body.phone_number)

    # Same error either way — never confirm/deny whether this phone number
    # is registered, only whether "phone + code" together checked out.
    if user is None:
        raise invalid_code

    approved = twilio_service.check_otp(body.phone_number, body.code)
    if not approved:
        raise invalid_code

    user.is_verified = True
    await user.save()

    access_token = security.create_access_token(str(user.id), is_admin=user.is_admin)
    refresh_token = security.create_refresh_token(str(user.id))

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/5minutes")
async def login(request: Request, body: LoginRequest):
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
    )

    user = await User.find_one(User.email == body.email)
    if user is None:
        raise invalid_credentials

    if not security.verify_password(body.password, user.hashed_password):
        raise invalid_credentials

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your phone number before logging in",
        )

    if user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended",
        )

    access_token = security.create_access_token(str(user.id), is_admin=user.is_admin)
    refresh_token = security.create_refresh_token(str(user.id))

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(body: RefreshRequest):
    payload = security.decode_token(body.refresh_token, settings.JWT_REFRESH_SECRET_KEY)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    user = await User.get(user_id) if user_id else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    access_token = security.create_access_token(str(user.id), is_admin=user.is_admin)
    return AccessTokenResponse(access_token=access_token)


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/5minutes")
async def forgot_password(request: Request, body: ForgotPasswordRequest):
    generic_message = MessageResponse(
        message="If that account exists, a verification code has been sent."
    )

    user = await User.find_one(User.email == body.email)
    if user is None:
        # Same response either way — never confirm/deny whether the email matched.
        return generic_message

    twilio_service.send_otp(user.phone_number)
    return generic_message


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest):
    invalid_code = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired code",
    )

    user = await User.find_one(User.email == body.email)
    if user is None:
        raise invalid_code

    approved = twilio_service.check_otp(user.phone_number, body.code)
    if not approved:
        raise invalid_code

    user.hashed_password = security.hash_password(body.new_password)
    await user.save()

    return MessageResponse(message="Password has been reset successfully.")


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "full_name": current_user.full_name,
        "email": current_user.email,
        "phone_number": current_user.phone_number,
        "is_verified": current_user.is_verified,
        "is_premium": current_user.is_premium,
        "is_admin": current_user.is_admin,
    }