from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.ledger_account import LedgerAccountOwnerType, LedgerAccountStatus


class LedgerAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_type: LedgerAccountOwnerType
    owner_user_id: str | None
    owner_archive_id: str | None
    balance_cents: int
    currency: str
    status: LedgerAccountStatus
    created_at: datetime
