from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.transaction import TransactionRead
from app.services import ledger_service

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("", response_model=list[TransactionRead])
def view_ledger(
    account_id: str | None = Query(default=None), db: Session = Depends(get_db)
) -> list[TransactionRead]:
    return ledger_service.list_transactions(db, ledger_account_id=account_id)
