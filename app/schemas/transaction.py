from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.transaction import TransactionStatus, TransactionType


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ledger_account_id: str
    settlement_id: str
    type: TransactionType
    amount_cents: int
    currency: str
    status: TransactionStatus
    created_at: datetime
