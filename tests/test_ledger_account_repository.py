import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base

# Import models so they register on Base.metadata before create_all runs.
from app.models import historical_archive, ledger_account, user  # noqa: F401
from app.repositories import ledger_account_repository


@pytest.fixture()
def SessionFactory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_adjust_balance_reflects_a_concurrent_writers_change_not_a_stale_read(SessionFactory):
    """
    Regression test for the lost-update bug: the original adjust_balance did
    `account.balance_cents += delta; db.commit()` in Python. If the account was
    already cached in a session's identity map, `db.get()` would return that
    stale cached object without re-querying, and the write would silently
    clobber whatever another session had already committed.

    This simulates exactly that: session A creates and caches the account,
    session B (a fully independent writer) commits its own +500 delta, then
    session A calls adjust_balance. The old code would return 100 (its own
    delta applied to the stale cached 0, discarding B's +500). The fix does the
    increment as a single atomic SQL UPDATE, so it can't be fooled by A's cache.
    """
    session_a = SessionFactory()
    account = ledger_account_repository.create_platform_account(session_a)
    session_a.commit()
    assert account.balance_cents == 0  # now cached in session_a's identity map at 0

    session_b = SessionFactory()
    ledger_account_repository.adjust_balance(session_b, account.id, 500)
    session_b.commit()
    session_b.close()

    updated = ledger_account_repository.adjust_balance(session_a, account.id, 100)
    session_a.commit()

    assert updated.balance_cents == 600  # both deltas applied, not just session_a's
    session_a.close()
