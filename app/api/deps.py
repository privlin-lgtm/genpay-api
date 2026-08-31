from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.api_client import ApiClient
from app.repositories import api_client_repository

__all__ = ["get_db", "require_api_key"]


def require_api_key(
    x_api_key: str | None = Header(default=None), db: Session = Depends(get_db)
) -> ApiClient:
    """
    Gates internal/financial routes (accounts, ledger, purchases, and every
    write endpoint) behind a per-caller API key, looked up by its hash rather
    than compared against one shared secret. This is intentionally still the
    minimum viable gate — a real deployment wants role scoping too (a
    researcher shouldn't be able to list every other researcher's balance) —
    but distinguishing *which* caller made a request is what makes actor
    attribution on ledger-affecting rows (Authorization.created_by_client_id)
    possible at all; a single shared key can't answer "who did this."

    Returns the resolved ApiClient so routes that need to stamp an actor can
    consume it directly; routes that only need the gate can use this as a
    router-level `dependencies=[Depends(require_api_key)]` and ignore the
    return value — FastAPI caches the dependency per request either way, so
    declaring it both ways in the same request doesn't run the lookup twice.

    The header is optional at the parameter level and checked manually so a
    missing key returns 401 like a wrong one, rather than FastAPI's default 422
    for a missing required header — 422 means "your request is malformed," 401
    means "you're not authenticated," and a missing key is the latter.

    Looking the key up by its hash (rather than comparing candidate keys one at
    a time) means there's no loop whose iteration count could leak which key
    matched, and the hash itself removes the "compare secrets character by
    character" timing concern hmac.compare_digest existed to prevent here.
    """
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    client = api_client_repository.get_by_key(db, x_api_key)
    if client is None or not client.is_active:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    return client
