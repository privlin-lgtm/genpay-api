from sqlalchemy.orm import Session

from app.models.user import UserRole
from app.repositories import research_record_repository, user_repository
from app.schemas.purchase import PurchaseResult
from app.schemas.webhook import CardAuthorizationEvent
from app.services.payment_service import purchase_record


def handle_card_authorization(db: Session, event: CardAuthorizationEvent) -> PurchaseResult:
    """Simulate a downstream card processor notifying us that a charge cleared."""
    if event.event_type != "card_authorization":
        raise ValueError(f"Unsupported event_type: {event.event_type}")

    record = research_record_repository.get_by_reference(db, event.record_id)
    if record is None:
        raise ValueError(f"Unknown record_id: {event.record_id}")

    user_id = event.user_id
    if user_id is None:
        researchers = [u for u in user_repository.list_all(db) if u.role == UserRole.researcher]
        if not researchers:
            raise ValueError("No researcher account available to settle against")
        user_id = researchers[0].id

    amount_cents = round(event.amount * 100)
    return purchase_record(db, research_record_id=record.id, user_id=user_id, amount_cents=amount_cents)
