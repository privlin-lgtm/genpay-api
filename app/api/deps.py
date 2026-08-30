import hmac

from fastapi import Header, HTTPException

from app.config import settings
from app.database.db import get_db

__all__ = ["get_db", "require_api_key"]


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """
    Gates internal/financial routes (accounts, ledger, purchases, and every
    write endpoint) behind a shared API key. This is intentionally the minimum
    viable gate — a real deployment wants per-caller keys and role scoping (a
    researcher shouldn't be able to list every other researcher's balance) —
    but "anyone on the internet can create a platform_admin user and read every
    ledger entry," which is where this app started, isn't acceptable for
    anything touching real money.

    The header is optional at the parameter level and checked manually so a
    missing key returns 401 like a wrong one, rather than FastAPI's default 422
    for a missing required header — 422 means "your request is malformed," 401
    means "you're not authenticated," and a missing key is the latter.

    Constant-time comparison (hmac.compare_digest) avoids leaking the correct
    key one character at a time via response-timing differences.
    """
    if x_api_key is None or not hmac.compare_digest(x_api_key, settings.internal_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
