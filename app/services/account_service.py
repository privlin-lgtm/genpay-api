from sqlalchemy.orm import Session

from app.models.ledger_account import LedgerAccount
from app.repositories import ledger_account_repository


def list_accounts(db: Session, limit: int = 50, offset: int = 0) -> list[LedgerAccount]:
    return ledger_account_repository.list_all(db, limit=limit, offset=offset)


def get_account(db: Session, account_id: str) -> LedgerAccount | None:
    return ledger_account_repository.get(db, account_id)
