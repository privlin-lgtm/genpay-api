from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.historical_archive import HistoricalArchive
from app.schemas.historical_archive import HistoricalArchiveCreate


def create(db: Session, data: HistoricalArchiveCreate) -> HistoricalArchive:
    archive = HistoricalArchive(
        name=data.name, description=data.description, owner_user_id=data.owner_user_id
    )
    db.add(archive)
    db.flush()
    db.refresh(archive)
    return archive


def get(db: Session, archive_id: str) -> HistoricalArchive | None:
    return db.get(HistoricalArchive, archive_id)


def list_all(db: Session, limit: int = 50, offset: int = 0) -> list[HistoricalArchive]:
    stmt = select(HistoricalArchive).order_by(HistoricalArchive.created_at).limit(limit).offset(offset)
    return list(db.scalars(stmt))
