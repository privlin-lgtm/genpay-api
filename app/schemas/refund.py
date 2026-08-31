from pydantic import BaseModel

from app.models.settlement import SettlementStatus
from app.schemas.transaction import TransactionRead


class RefundResult(BaseModel):
    authorization_id: str
    settlement_id: str
    settlement_status: SettlementStatus
    refunded_cents: int
    reason: str | None
    transactions: list[TransactionRead]
