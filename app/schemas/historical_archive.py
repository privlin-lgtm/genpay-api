from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HistoricalArchiveCreate(BaseModel):
    name: str
    description: str | None = None
    owner_user_id: str | None = None


class HistoricalArchiveRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    owner_user_id: str | None
    created_at: datetime
