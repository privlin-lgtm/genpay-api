import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.authorization import Authorization, AuthorizationStatus


def create(db: Session, research_record_id: str, user_id: str, amount_cents: int) -> Authorization:
    """Synchronous demo path: authorize and hold in one step (no separate approval webhook)."""
    authorization = Authorization(
        research_record_id=research_record_id,
        user_id=user_id,
        amount_cents=amount_cents,
        external_reference=f"sim_card_auth_{uuid.uuid4().hex[:12]}",
        status=AuthorizationStatus.authorized,
    )
    db.add(authorization)
    db.commit()
    db.refresh(authorization)
    return authorization


def create_pending(
    db: Session, research_record_id: str, user_id: str, amount_cents: int, external_reference: str
) -> Authorization:
    """Async processor path: an authorization.created event arrives before approval/decline is known."""
    authorization = Authorization(
        research_record_id=research_record_id,
        user_id=user_id,
        amount_cents=amount_cents,
        external_reference=external_reference,
        status=AuthorizationStatus.pending,
    )
    db.add(authorization)
    db.commit()
    db.refresh(authorization)
    return authorization


def mark_approved(db: Session, authorization: Authorization) -> Authorization:
    authorization.status = AuthorizationStatus.authorized
    db.commit()
    db.refresh(authorization)
    return authorization


def mark_declined(db: Session, authorization: Authorization, reason: str) -> Authorization:
    authorization.status = AuthorizationStatus.declined
    authorization.decline_reason = reason
    db.commit()
    db.refresh(authorization)
    return authorization


def get(db: Session, authorization_id: str) -> Authorization | None:
    return db.get(Authorization, authorization_id)


def get_by_external_reference(db: Session, external_reference: str) -> Authorization | None:
    return db.scalar(select(Authorization).where(Authorization.external_reference == external_reference))
