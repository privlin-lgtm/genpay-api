from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.settlement import Settlement, SettlementStatus


def create(db: Session, authorization_id: str, settled_amount_cents: int) -> Settlement:
    settlement = Settlement(
        authorization_id=authorization_id,
        settled_amount_cents=settled_amount_cents,
        status=SettlementStatus.settled,
    )
    db.add(settlement)
    db.flush()
    db.refresh(settlement)
    return settlement


def get(db: Session, settlement_id: str) -> Settlement | None:
    return db.get(Settlement, settlement_id)


def get_by_authorization(db: Session, authorization_id: str) -> Settlement | None:
    return db.scalar(select(Settlement).where(Settlement.authorization_id == authorization_id))
