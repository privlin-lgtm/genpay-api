from sqlalchemy.orm import Session

from app.models.research_record import ResearchRecord
from app.repositories import research_record_repository
from app.schemas.research_record import ResearchRecordCreate


def create_record(db: Session, data: ResearchRecordCreate) -> ResearchRecord:
    return research_record_repository.create(db, data)


def get_record(db: Session, record_id: str) -> ResearchRecord | None:
    return research_record_repository.get(db, record_id)


def get_record_by_reference(db: Session, record_reference: str) -> ResearchRecord | None:
    return research_record_repository.get_by_reference(db, record_reference)


def list_records(db: Session, limit: int = 50, offset: int = 0) -> list[ResearchRecord]:
    return research_record_repository.list_all(db, limit=limit, offset=offset)
