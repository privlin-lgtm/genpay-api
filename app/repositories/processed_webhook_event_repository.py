from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.processed_webhook_event import ProcessedWebhookEvent


def try_claim(db: Session, event_id: str, event_type: str) -> bool:
    """
    Atomically claim an event_id for processing. Returns True if this call won
    the claim, False if another delivery (concurrent, or a prior one already
    committed) already holds it.

    Attempts the insert directly rather than a separate has_processed() SELECT
    followed by an insert: a pre-check has a race window between the two calls
    that two concurrent deliveries of the same event_id could both pass before
    either commits. Making the insert itself the synchronization point closes
    that window — the database's own unique constraint is authoritative.

    On a collision, rolls back immediately: a failed flush leaves the session's
    transaction unusable until it's rolled back or the failing statement's
    effects are otherwise undone. This is only safe because try_claim is always
    the first write in its request — rolling back here doesn't discard any
    other work. (An earlier version wrapped the insert in db.begin_nested() to
    scope that rollback to just this statement via a SAVEPOINT, but a later
    full-session rollback was found not to reliably undo a released SAVEPOINT's
    work in this environment — verified with a raw-SQL row count, not just the
    ORM's identity map. Since the plain-flush version below doesn't depend on
    that behavior, it doesn't need the SAVEPOINT at all.)

    The rest of the request's writes still commit or roll back together as
    normal via get_db(): if the caller's handler fails after a successful claim
    here, that failure's rollback correctly undoes this insert too, so the
    event_id isn't permanently burned by a failed attempt.
    """
    db.add(ProcessedWebhookEvent(event_id=event_id, event_type=event_type))
    try:
        db.flush()
        return True
    except IntegrityError:
        db.rollback()
        return False
