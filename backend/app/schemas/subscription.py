"""Pydantic schemas for the subscriptions/payments API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SubscriptionResponse(BaseModel):
    plan: str
    status: str
    start_date: datetime
    end_date: Optional[datetime] = None


class UpgradeOrderResponse(BaseModel):
    """
    Returned by POST /subscriptions/upgrade so the frontend can open
    Razorpay's Checkout widget directly — deliberately includes
    RAZORPAY_KEY_ID (the public key; it's meant to be client-visible) but
    never RAZORPAY_KEY_SECRET or RAZORPAY_WEBHOOK_SECRET.
    """
    order_id: str
    amount: int  # paise
    currency: str
    razorpay_key_id: str