"""
Shared slowapi Limiter instance, keyed by client IP.

A single shared Limiter (rather than one per router) means rate-limit state
is consistent across the whole app and main.py only needs to register one
exception handler.
"""

# Phase 2/4 rate limits were keyed by client IP (slowapi's default
# get_remote_address). Phase 5's /calls/initiate needs a per-QR-TOKEN limit
# instead: the abuse case is many different people (many IPs) repeatedly
# calling the SAME vehicle's owner, not one IP hitting many endpoints.
#
# slowapi lets you pass a custom key_func on a per-route @limiter.limit(...)
# call. This function pulls `token` out of the parsed request body.

from slowapi import Limiter
from slowapi.util import get_remote_address

from fastapi import Request


limiter = Limiter(key_func=get_remote_address)

async def get_token_from_body(request: Request) -> str:
    """
    Rate-limit key function: extracts the QR token from the JSON request
    body of POST /calls/initiate, so the 3-per-10-minutes limit is scoped to
    "this vehicle's QR code" rather than "this caller's IP address".
 
    Falls back to remote address if the body can't be parsed (defensive —
    shouldn't happen since FastAPI's own validation runs on the same body,
    but a rate limiter must never itself throw on a malformed request).
    """
    try:
        body = await request.json()
        token = body.get("token")
        if token:
            return f"call-initiate:{token}"
    except Exception:
        pass
    from slowapi.util import get_remote_address
 
    return get_remote_address(request)
