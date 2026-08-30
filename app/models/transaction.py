import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class TransactionType(str, enum.Enum):
    debit = "debit"
    credit = "credit"


class TransactionStatus(str, enum.Enum):
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
