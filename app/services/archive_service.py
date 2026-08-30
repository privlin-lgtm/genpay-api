from sqlalchemy.orm import Session

from app.models.historical_archive import HistoricalArchive
from app.repositories import historical_archive_repository, ledger_account_repository
from app.schemas.historical_archive import HistoricalArchiveCreate


def create_archive(db: Session, data: HistoricalArchiveCreate) -> HistoricalArchive:
    """Create an archive and provision its ledger account in one step."""
    archive = historical_archive_repository.create(db, data)
    ledger_account_repository.create_for_archive(db, archive.id)
    return archive


def get_archive(db: Session, archive_id: str) -> HistoricalArchive | None:
    return historical_archive_repository.get(db, archive_id)


def list_archives(db: Session) -> list[HistoricalArchive]:
    return historical_archive_repository.list_all(db)
