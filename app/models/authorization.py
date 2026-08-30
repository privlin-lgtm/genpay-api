import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class AuthorizationStatus(str, enum.Enum):
    pending = "pending"
    authorized = "authorized"
    declined = "declined"
    expired = "expired"


class Authorization(Base):
    __tablename__ = "authorizations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    research_record_id: Mapped[str] = mapped_column(
        String, ForeignKey("research_records.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    external_reference: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    decline_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[AuthorizationStatus] = mapped_column(
        SAEnum(AuthorizationStatus), nullable=False, default=AuthorizationStatus.authorized
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    research_record: Mapped["ResearchRecord"] = relationship(back_populates="authorizations")
    user: Mapped["User"] = relationship(back_populates="authorizations")
    settlement: Mapped["Settlement"] = relationship(back_populates="authorization", uselist=False)
