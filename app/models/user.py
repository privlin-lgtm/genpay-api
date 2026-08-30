import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class UserRole(str, enum.Enum):
    researcher = "researcher"
    transcriptionist = "transcriptionist"
    platform_admin = "platform_admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    archives: Mapped[list["HistoricalArchive"]] = relationship(back_populates="owner")
    transcribed_records: Mapped[list["ResearchRecord"]] = relationship(back_populates="transcriptionist")
    authorizations: Mapped[list["Authorization"]] = relationship(back_populates="user")
    ledger_account: Mapped["LedgerAccount"] = relationship(back_populates="owner_user", uselist=False)
