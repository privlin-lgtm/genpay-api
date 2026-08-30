from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories import ledger_account_repository
from app.schemas.ledger_account import LedgerAccountRead

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[LedgerAccountRead])
def list_accounts(db: Session = Depends(get_db)) -> list[LedgerAccountRead]:
    return ledger_account_repository.list_all(db)


@router.get("/{account_id}", response_model=LedgerAccountRead)
def get_account(account_id: str, db: Session = Depends(get_db)) -> LedgerAccountRead:
    account = ledger_account_repository.get(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account
