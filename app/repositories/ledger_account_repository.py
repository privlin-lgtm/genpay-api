from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.ledger_account import LedgerAccount, LedgerAccountOwnerType


def create_for_user(db: Session, user_id: str, currency: str = "USD") -> LedgerAccount:
    account = LedgerAccount(owner_type=LedgerAccountOwnerType.user, owner_user_id=user_id, currency=currency)
    db.add(account)
    db.flush()
    db.refresh(account)
    return account


def create_for_archive(db: Session, archive_id: str, currency: str = "USD") -> LedgerAccount:
    account = LedgerAccount(
        owner_type=LedgerAccountOwnerType.archive, owner_archive_id=archive_id, currency=currency
    )
    db.add(account)
    db.flush()
    db.refresh(account)
    return account


def create_platform_account(db: Session, currency: str = "USD") -> LedgerAccount:
    account = LedgerAccount(owner_type=LedgerAccountOwnerType.platform, currency=currency)
    db.add(account)
    db.flush()
    db.refresh(account)
    return account


def get(db: Session, account_id: str) -> LedgerAccount | None:
    return db.get(LedgerAccount, account_id)


def get_by_owner_user(db: Session, user_id: str) -> LedgerAccount | None:
    return db.scalar(select(LedgerAccount).where(LedgerAccount.owner_user_id == user_id))


def get_by_owner_archive(db: Session, archive_id: str) -> LedgerAccount | None:
    return db.scalar(select(LedgerAccount).where(LedgerAccount.owner_archive_id == archive_id))


def get_platform_account(db: Session) -> LedgerAccount | None:
    return db.scalar(
        select(LedgerAccount).where(LedgerAccount.owner_type == LedgerAccountOwnerType.platform)
    )


def list_all(db: Session, limit: int = 50, offset: int = 0) -> list[LedgerAccount]:
    stmt = select(LedgerAccount).order_by(LedgerAccount.created_at).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def adjust_balance(db: Session, account_id: str, delta_cents: int) -> LedgerAccount:
    """
    Applies the delta as a single atomic SQL UPDATE (balance = balance + delta)
    rather than reading the balance into Python and writing it back — the
    read-modify-write version loses updates under concurrent writers (two
    transactions both read balance=1000, both compute +60, both write 1060,
    one purchase's revenue silently vanishes). An in-database increment can't
    lose an update: the DB serializes concurrent writers on the same row.
    """
    db.execute(
        update(LedgerAccount)
        .where(LedgerAccount.id == account_id)
        .values(balance_cents=LedgerAccount.balance_cents + delta_cents)
    )
    account = db.get(LedgerAccount, account_id)
    if account is None:
        raise ValueError(f"Ledger account not found: {account_id}")
    db.refresh(account)  # the bulk UPDATE bypassed the ORM, so the identity map is stale
    return account
