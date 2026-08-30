"""
Application configuration.

Settings are read from a `.env` file in the backend/ directory (see .env.example
for the full list of variables with explanations). Using pydantic-settings means
every setting is validated and typed at startup instead of failing deep inside
some unrelated request handler later.
"""
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Core / Phase 0 ---
    MONGODB_URI: str
    JWT_SECRET_KEY: str
    JWT_REFRESH_SECRET_KEY: str
    FRONTEND_URL: str = "http://127.0.0.1:3000"
    BACKEND_URL: str = "http://127.0.0.1:8000"

    # CORS: comma-separated list of allowed origins. Defaults to local dev only;
    # production deployments add the real frontend domain via the env var without
    # touching code (see Phase 14 hardening pass).
    ALLOWED_ORIGINS: str = "http://127.0.0.1:3000"

    # --- Phase 2: Auth (OTP + JWT) ---
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_VERIFY_SERVICE_SID: str

    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # --- Phase 4: QR codes ---
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # --- Phase 5: Twilio Voice (call masking) ---
    TWILIO_PHONE_NUMBER: str = ""  # the masking number both scanner and owner see as caller ID4

    # --- Phase 6: Twilio Send Message (Report an Issue) ---
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "shivamgupta992909@gmail.com"
    FIREBASE_CREDENTIALS_JSON: str = ""

    # --- Phase 9: Subscriptions & Payments (Razorpay) ---
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Premium plan price, in paise (smallest INR unit — ₹199.00 = 19900 paise).
    # Kept as a plain settable int (not hardcoded in the router) so pricing can
    # change via .env without a code deploy.
    PREMIUM_MONTHLY_PRICE_PAISE: int = 19900

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> List[str]:
        """Parsed list form of ALLOWED_ORIGINS for CORSMiddleware."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    # --- Admin bootstrapping ---
    # Comma-separated list of email addresses that are automatically granted
    # is_admin=True at registration time. This is the ONLY way an account
    # becomes an admin — there is no public "become admin" endpoint, and the
    # frontend never grants admin access on its own; it only reflects what
    # the backend already decided at registration.
    ADMIN_EMAILS: str = ""

    @property
    def admin_emails_list(self) -> list[str]:
        return [e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()]


# Single shared settings instance, imported wherever config values are needed.
settings = Settings()
