from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction, TransactionStatus, TransactionType


def create(
    db: Session,
    ledger_account_id: str,
    settlement_id: str,
    type_: TransactionType,
    amount_cents: int,
    status: TransactionStatus = TransactionStatus.pending,
) -> Transaction:
    txn = Transaction(
        ledger_account_id=ledger_account_id,
        settlement_id=settlement_id,
        type=type_,
        amount_cents=amount_cents,
        status=status,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def get(db: Session, transaction_id: str) -> Transaction | None:
    return db.get(Transaction, transaction_id)


def list_all(db: Session, ledger_account_id: str | None = None) -> list[Transaction]:
    stmt = select(Transaction)
    if ledger_account_id:
        stmt = stmt.where(Transaction.ledger_account_id == ledger_account_id)
    return list(db.scalars(stmt))


def list_for_settlement(db: Session, settlement_id: str) -> list[Transaction]:
    return list(db.scalars(select(Transaction).where(Transaction.settlement_id == settlement_id)))
