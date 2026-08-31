import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base

if TYPE_CHECKING:
    from app.models.authorization import Authorization


class ApiClient(Base):
    """
    A caller identity, distinct from the shared X-API-Key model this replaces.
    Storing api_key_hash (not the raw key) means a DB leak doesn't hand out
    usable credentials — the same reasoning as hashing passwords, applied to
    API keys.
    """

    __tablename__ = "api_clients"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    authorizations: Mapped[list["Authorization"]] = relationship(back_populates="created_by_client")
