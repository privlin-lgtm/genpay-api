from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ledger_account import LedgerAccount, LedgerAccountOwnerType


def create_for_user(db: Session, user_id: str, currency: str = "USD") -> LedgerAccount:
    account = LedgerAccount(owner_type=LedgerAccountOwnerType.user, owner_user_id=user_id, currency=currency)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def create_for_archive(db: Session, archive_id: str, currency: str = "USD") -> LedgerAccount:
    account = LedgerAccount(
        owner_type=LedgerAccountOwnerType.archive, owner_archive_id=archive_id, currency=currency
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def create_platform_account(db: Session, currency: str = "USD") -> LedgerAccount:
    account = LedgerAccount(owner_type=LedgerAccountOwnerType.platform, currency=currency)
    db.add(account)
    db.commit()
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


def list_all(db: Session) -> list[LedgerAccount]:
    return list(db.scalars(select(LedgerAccount)))


def adjust_balance(db: Session, account_id: str, delta_cents: int) -> LedgerAccount:
    account = db.get(LedgerAccount, account_id)
    account.balance_cents += delta_cents
    db.commit()
    db.refresh(account)
    return account
