import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class ResearchRecord(Base):
    __tablename__ = "research_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    archive_id: Mapped[str] = mapped_column(String, ForeignKey("historical_archives.id"), nullable=False)
    record_reference: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    transcriptionist_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    archive: Mapped["HistoricalArchive"] = relationship(back_populates="records")
    transcriptionist: Mapped["User"] = relationship(back_populates="transcribed_records")
    authorizations: Mapped[list["Authorization"]] = relationship(back_populates="research_record")
