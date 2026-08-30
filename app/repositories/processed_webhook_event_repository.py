from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.processed_webhook_event import ProcessedWebhookEvent


def has_processed(db: Session, event_id: str) -> bool:
    return db.get(ProcessedWebhookEvent, event_id) is not None


def mark_processed(db: Session, event_id: str, event_type: str) -> bool:
    """
    Record an event_id as processed. Returns False (instead of raising) if another
    request already recorded it first — the race between check-and-insert is real
    under concurrent delivery, and the unique constraint is the actual guard.
    """
    db.add(ProcessedWebhookEvent(event_id=event_id, event_type=event_type))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False
