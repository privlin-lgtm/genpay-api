import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base

if TYPE_CHECKING:
    from app.models.api_client import ApiClient
    from app.models.research_record import ResearchRecord
    from app.models.settlement import Settlement
    from app.models.user import User


class AuthorizationStatus(enum.StrEnum):
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
    # Who/what initiated this purchase: the caller's ApiClient for POST /purchase,
    # or the seeded "processor-webhook" system client for the async webhook path.
    # Nullable because it's an audit-trail addition, not a business invariant —
    # a purchase without a known actor is unusual, not invalid.
    created_by_client_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("api_clients.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    research_record: Mapped["ResearchRecord"] = relationship(back_populates="authorizations")
    user: Mapped["User"] = relationship(back_populates="authorizations")
    settlement: Mapped["Settlement"] = relationship(back_populates="authorization", uselist=False)
    created_by_client: Mapped["ApiClient"] = relationship(back_populates="authorizations")
