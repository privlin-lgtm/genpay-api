from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.research_record import ResearchRecord
from app.schemas.research_record import ResearchRecordCreate


def create(db: Session, data: ResearchRecordCreate) -> ResearchRecord:
    record = ResearchRecord(
        archive_id=data.archive_id,
        record_reference=data.record_reference,
        title=data.title,
        price_cents=data.price_cents,
        transcriptionist_user_id=data.transcriptionist_user_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get(db: Session, record_id: str) -> ResearchRecord | None:
    return db.get(ResearchRecord, record_id)


def get_by_reference(db: Session, record_reference: str) -> ResearchRecord | None:
    return db.scalar(select(ResearchRecord).where(ResearchRecord.record_reference == record_reference))


def list_all(db: Session) -> list[ResearchRecord]:
    return list(db.scalars(select(ResearchRecord)))
