from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.authorization import AuthorizationStatus
from app.models.settlement import SettlementStatus
from app.schemas.transaction import TransactionRead


class PurchaseRequest(BaseModel):
    research_record_id: str
    user_id: str


class PurchaseResult(BaseModel):
    authorization_id: str
    settlement_id: str
    authorization_status: AuthorizationStatus
    settlement_status: SettlementStatus
    record_id: str
    total_cents: int
    archive_cents: int
    transcriptionist_cents: int
    platform_cents: int
    transactions: list[TransactionRead]


class PurchaseDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    research_record_id: str
    user_id: str
    amount_cents: int
    external_reference: str
    status: AuthorizationStatus
    created_at: datetime
