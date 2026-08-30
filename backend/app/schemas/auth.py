"""
Request/response schemas for the /auth/* endpoints.

Validation lives here rather than in the router bodies so it's declarative,
reusable, and testable in isolation from any DB/Twilio calls.
"""
import re

import phonenumbers
from pydantic import BaseModel, EmailStr, field_validator


def _validate_password_strength(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")
    return password


def _validate_and_normalize_phone(phone_number: str) -> str:
    try:
        parsed = phonenumbers.parse(phone_number, None)
    except phonenumbers.NumberParseException:
        raise ValueError(
            "Phone number must be in E.164 format, e.g. +919876543210"
        )
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(
            "Phone number must be in E.164 format, e.g. +919876543210"
        )
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


# --- Register ---

class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: str
    password: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_and_normalize_phone(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Full name cannot be empty")
        return v.strip()


class MessageResponse(BaseModel):
    message: str


# --- Verify OTP ---

class VerifyOtpRequest(BaseModel):
    phone_number: str
    code: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_and_normalize_phone(v)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# --- Login ---

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# --- Refresh ---

class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Forgot / Reset password ---

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_strength(v)
