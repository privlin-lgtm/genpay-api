import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class SettlementStatus(str, enum.Enum):
    settled = "settled"
    failed = "failed"
    reversed = "reversed"


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    authorization_id: Mapped[str] = mapped_column(
        String, ForeignKey("authorizations.id"), unique=True, nullable=False
    )
    settled_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SettlementStatus] = mapped_column(
        SAEnum(SettlementStatus), nullable=False, default=SettlementStatus.settled
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    authorization: Mapped["Authorization"] = relationship(back_populates="settlement")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="settlement")
