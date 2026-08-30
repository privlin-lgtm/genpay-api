import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database.db import Base, get_db
from app.database.seed_data import seed
from app.main import app

# Import models so they register on Base.metadata before create_all runs.
from app.models import (  # noqa: F401
    authorization,
    historical_archive,
    idempotency_key,
    ledger_account,
    processed_webhook_event,
    research_record,
    settlement,
    transaction,
    user,
)

# Defaults to an isolated in-memory SQLite DB per test. CI also runs this exact
# suite against a real Postgres service by setting TEST_DATABASE_URL — the
# atomic-UPDATE fix in ledger_account_repository and the SAVEPOINT/rollback
# behavior documented in the idempotency repositories were both motivated by
# Postgres semantics, so "the tests pass" should mean that on Postgres too, not
# just on SQLite's much more forgiving single-writer locking.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture()
def client():
    if TEST_DATABASE_URL.startswith("sqlite"):
        engine = create_engine(
            TEST_DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(TEST_DATABASE_URL)

    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # drop_all first: against a persistent DB (Postgres) a previous crashed run
    # could have left tables behind; against a fresh :memory: SQLite it's a no-op.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        # Mirrors app.database.db.get_db's commit-on-success/rollback-on-exception
        # behavior: repositories only flush(), so without this, nothing a request
        # writes would ever be visible to the next request's session.
        db = TestSessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = TestSessionLocal()
    try:
        seed(db)
    finally:
        db.close()

    with TestClient(app) as test_client:
        test_client.headers.update(
            {"X-API-Key": settings.internal_api_key, "Idempotency-Key": "test-default-idempotency-key"}
        )
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
