from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResearchRecordCreate(BaseModel):
    archive_id: str
    record_reference: str
    title: str
    price_cents: int
    transcriptionist_user_id: str | None = None


class ResearchRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    archive_id: str
    record_reference: str
    title: str
    price_cents: int
    transcriptionist_user_id: str | None
    created_at: datetime
