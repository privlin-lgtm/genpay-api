from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class IdempotencyKey(Base):
    """
    One row per Idempotency-Key seen on POST /purchase. A retried request with
    the same key returns the stored response instead of re-running the purchase
    — without this, a client retry after a timed-out request (the client can
    never be sure whether the first attempt actually landed) creates a second
    Authorization + Settlement + real ledger postings for the same purchase.
    """

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    # Null between the claim (before the purchase runs) and the result being
    # stored (after it completes) — see idempotency_key_repository.try_claim.
    response_body: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
