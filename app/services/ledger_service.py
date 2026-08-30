from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.repositories import ledger_account_repository, transaction_repository


@dataclass(frozen=True)
class LedgerEntry:
    ledger_account_id: str
    type: TransactionType
    amount_cents: int


def post_entries(db: Session, settlement_id: str, entries: list[LedgerEntry]) -> list[Transaction]:
    """
    Post a balanced set of ledger entries for one settlement: create each Transaction
    already 'posted' and apply its effect to the owning account's balance in the same
    step. Callers are responsible for ensuring debits == credits before calling this.
    """
    debit_total = sum(e.amount_cents for e in entries if e.type == TransactionType.debit)
    credit_total = sum(e.amount_cents for e in entries if e.type == TransactionType.credit)
    if debit_total != credit_total:
        raise ValueError(f"Unbalanced entries: debits={debit_total} credits={credit_total}")

    transactions = []
    for entry in entries:
        txn = transaction_repository.create(
            db,
            ledger_account_id=entry.ledger_account_id,
            settlement_id=settlement_id,
            type_=entry.type,
            amount_cents=entry.amount_cents,
            status=TransactionStatus.posted,
        )
        delta = entry.amount_cents if entry.type == TransactionType.credit else -entry.amount_cents
        ledger_account_repository.adjust_balance(db, entry.ledger_account_id, delta)
        transactions.append(txn)

    return transactions


def list_transactions(
    db: Session, ledger_account_id: str | None = None, limit: int = 50, offset: int = 0
) -> list[Transaction]:
    return transaction_repository.list_all(db, ledger_account_id=ledger_account_id, limit=limit, offset=offset)
