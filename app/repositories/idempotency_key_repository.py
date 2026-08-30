from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.idempotency_key import IdempotencyKey


def get(db: Session, key: str) -> str | None:
    """
    Returns the stored response for a completed request under this key, or None
    if either no request has used this key yet, or one is still in flight (its
    claim row exists but response_body hasn't been filled in). Both of those
    cases are handled correctly by the caller: falling through to try_claim(),
    which only succeeds for the genuinely-unclaimed case.
    """
    record = db.get(IdempotencyKey, key)
    return record.response_body if record else None


def try_claim(db: Session, key: str) -> bool:
    """
    Atomically claim `key` before the request is processed (not after — claiming
    after processing leaves a window where two concurrent requests under the
    same key both pass a pre-check and both execute the real side effects, which
    is exactly what an idempotency key exists to prevent).

    See processed_webhook_event_repository.try_claim's docstring for why this is
    a plain insert+flush rather than one scoped by db.begin_nested(): a released
    SAVEPOINT was found not to reliably survive-or-not-survive a later full
    rollback as expected in this environment, and a plain flush doesn't have
    that problem. This is only safe as the first write in its request.
    """
    db.add(IdempotencyKey(key=key, response_body=None))
    try:
        db.flush()
        return True
    except IntegrityError:
        db.rollback()
        return False


def store_result(db: Session, key: str, response_body: str) -> None:
    record = db.get(IdempotencyKey, key)
    if record is None:
        raise ValueError(f"No claim exists for idempotency key: {key}")
    record.response_body = response_body
    db.flush()
