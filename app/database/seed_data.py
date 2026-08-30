from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import UserRole
from app.repositories import ledger_account_repository
from app.schemas.historical_archive import HistoricalArchiveCreate
from app.schemas.research_record import ResearchRecordCreate
from app.schemas.user import UserCreate
from app.services import archive_service, record_service, user_service


def seed(db: Session) -> None:
    """
    Populate demo data: a platform account, an archive, a transcriptionist, a
    researcher, and one purchasable census record — enough to exercise the full
    purchase flow out of the box.

    Runs outside any HTTP request, so unlike everything under app/api/ it must
    manage its own transaction (repositories only flush(); get_db()'s commit
    doesn't apply here). The check-then-act on get_platform_account() has a race
    window if two app instances cold-start at the same time — both could pass the
    check before either commits. Rather than trying to close that window, this
    just treats the resulting unique-constraint violation (on User.email) as
    "someone else already seeded it" and moves on.
    """
    if ledger_account_repository.get_platform_account(db) is not None:
        return

    try:
        ledger_account_repository.create_platform_account(db)

        archive = archive_service.create_archive(
            db,
            HistoricalArchiveCreate(
                name="National Census Archive",
                description="Digitized census records for genealogy research.",
            ),
        )

        transcriptionist = user_service.create_user(
            db, UserCreate(name="Mark Reyes", email="mark@example.com", role=UserRole.transcriptionist)
        )

        user_service.create_user(
            db, UserCreate(name="Jane Ancestry", email="jane@example.com", role=UserRole.researcher)
        )

        record_service.create_record(
            db,
            ResearchRecordCreate(
                archive_id=archive.id,
                record_reference="CENSUS-1880-004",
                title="1880 Census, District 4",
                price_cents=599,
                transcriptionist_user_id=transcriptionist.id,
            ),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
