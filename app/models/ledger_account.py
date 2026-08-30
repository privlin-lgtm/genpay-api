import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base

if TYPE_CHECKING:
    from app.models.historical_archive import HistoricalArchive
    from app.models.transaction import Transaction
    from app.models.user import User


class LedgerAccountOwnerType(enum.StrEnum):
    user = "user"
    archive = "archive"
    platform = "platform"


class LedgerAccountStatus(enum.StrEnum):
    active = "active"
    suspended = "suspended"
    closed = "closed"


class LedgerAccount(Base):
    """
    owner_user_id / owner_archive_id are separate nullable FKs (rather than a single
    generic owner_id) so the database can enforce referential integrity on whichever
    owner is set. owner_type is the discriminator; the check constraint below ensures
    exactly one owner column is populated, matching owner_type ('platform' means both
    are null).
    """

    __tablename__ = "ledger_accounts"
    __table_args__ = (
        CheckConstraint(
            "(owner_type = 'user' AND owner_user_id IS NOT NULL AND owner_archive_id IS NULL) OR "
            "(owner_type = 'archive' AND owner_archive_id IS NOT NULL AND owner_user_id IS NULL) OR "
            "(owner_type = 'platform' AND owner_user_id IS NULL AND owner_archive_id IS NULL)",
            name="ck_ledger_account_owner_matches_type",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_type: Mapped[LedgerAccountOwnerType] = mapped_column(SAEnum(LedgerAccountOwnerType), nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id"), unique=True, nullable=True
    )
    owner_archive_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("historical_archives.id"), unique=True, nullable=True
    )
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    status: Mapped[LedgerAccountStatus] = mapped_column(
        SAEnum(LedgerAccountStatus), nullable=False, default=LedgerAccountStatus.active
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner_user: Mapped["User"] = relationship(back_populates="ledger_account")
    owner_archive: Mapped["HistoricalArchive"] = relationship(back_populates="ledger_account")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="ledger_account")
