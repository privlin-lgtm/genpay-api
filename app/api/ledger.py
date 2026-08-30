from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_api_key
from app.schemas.transaction import TransactionRead
from app.services import ledger_service

router = APIRouter(prefix="/ledger", tags=["ledger"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[TransactionRead])
def view_ledger(
    account_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[TransactionRead]:
    return ledger_service.list_transactions(db, ledger_account_id=account_id, limit=limit, offset=offset)
