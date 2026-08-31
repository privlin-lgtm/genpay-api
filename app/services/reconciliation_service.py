from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ledger_account import LedgerAccount
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.schemas.reconciliation import AccountDiscrepancy, ReconciliationReport


def reconcile_all(db: Session) -> ReconciliationReport:
    """
    Verifies, for every ledger account, that balance_cents actually equals the sum
    of its transaction history — the invariant adjust_balance's atomic UPDATE is
    supposed to guarantee at write time. This checks it holds *after* the fact,
    independent of however it got there: a bug in a future code path, a manual DB
    edit, or a bypassed service layer would all show up here even though none of
    them would be caught by the write-time invariant alone.

    Every 'posted' or 'reversed' transaction counts — adjust_balance was called
    unconditionally when each one was created, regardless of what its status is
    now. 'reversed' means "a later transaction offset this one," not "this one's
    effect on the balance never happened": a refund posts new transactions to
    undo the original's effect rather than un-applying the original, so both the
    original and its reversal remain real, permanent contributions to the
    account's history. Only 'pending' is excluded, since nothing in this
    codebase currently creates a transaction without also immediately applying
    it — a status this check would need to start honoring if that ever changes.
    """
    accounts = list(db.scalars(select(LedgerAccount)))
    discrepancies = []

    for account in accounts:
        computed = _computed_balance(db, account.id)
        if computed != account.balance_cents:
            discrepancies.append(
                AccountDiscrepancy(
                    ledger_account_id=account.id,
                    owner_type=account.owner_type.value,
                    stored_balance_cents=account.balance_cents,
                    computed_balance_cents=computed,
                    drift_cents=account.balance_cents - computed,
                )
            )

    return ReconciliationReport(accounts_checked=len(accounts), discrepancies=discrepancies)


def _computed_balance(db: Session, ledger_account_id: str) -> int:
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.ledger_account_id == ledger_account_id,
            Transaction.status != TransactionStatus.pending,
        )
    )
    balance = 0
    for txn in transactions:
        balance += txn.amount_cents if txn.type == TransactionType.credit else -txn.amount_cents
    return balance
