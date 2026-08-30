from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class ProcessedWebhookEvent(Base):
    """
    One row per successfully processed webhook event_id. Its primary key doubles as
    the idempotency guard: a duplicate delivery of the same event_id fails to insert
    (unique constraint) rather than re-running the handler.
    """

    __tablename__ = "processed_webhook_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
