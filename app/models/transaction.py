import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base

if TYPE_CHECKING:
    from app.models.ledger_account import LedgerAccount
    from app.models.settlement import Settlement


class TransactionType(enum.StrEnum):
    debit = "debit"
    credit = "credit"


class TransactionStatus(enum.StrEnum):
    pending = "pending"
    posted = "posted"
    reversed = "reversed"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ledger_account_id: Mapped[str] = mapped_column(
        String, ForeignKey("ledger_accounts.id"), nullable=False, index=True
    )
    settlement_id: Mapped[str] = mapped_column(
        String, ForeignKey("settlements.id"), nullable=False, index=True
    )
    type: Mapped[TransactionType] = mapped_column(SAEnum(TransactionType), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus), nullable=False, default=TransactionStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ledger_account: Mapped["LedgerAccount"] = relationship(back_populates="transactions")
    settlement: Mapped["Settlement"] = relationship(back_populates="transactions")
