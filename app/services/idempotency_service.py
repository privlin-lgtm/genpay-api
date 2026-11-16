"""
Idempotency-Key handling for POST /purchase.

Thin pass-through to idempotency_key_repository so the API layer never touches
a repository directly. The semantics (claim *before* processing; the claim
lives in the request's transaction, so a failed attempt rolls it back and the
key isn't burned) are unchanged and documented in the repository.
"""

from sqlalchemy.orm import Session

from app.repositories import idempotency_key_repository


def get_cached_result(db: Session, key: str) -> str | None:
    return idempotency_key_repository.get(db, key)


def try_claim(db: Session, key: str) -> bool:
    return idempotency_key_repository.try_claim(db, key)


def store_result(db: Session, key: str, response_body: str) -> None:
    idempotency_key_repository.store_result(db, key, response_body)
