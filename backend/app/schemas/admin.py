from typing import Optional

from pydantic import BaseModel


class SuspendUserRequest(BaseModel):
    suspended: bool


class RenewSubscriptionRequest(BaseModel):
    """Admin-triggered subscription renewal/grant.

    plan: which plan to set the user to ("free" or "premium"). Defaults to
    "premium" since that's the common case (comping/renewing a premium
    subscription manually — e.g. support resolving a payment-gateway issue).
    days: how many days from now the new period should run for. Ignored
    (end_date left None) when plan == "free".
    """
    plan: str = "premium"
    days: int = 30
    reason: Optional[str] = None

    