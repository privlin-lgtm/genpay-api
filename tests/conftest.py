import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base, get_db
from app.main import app
from app.database.seed_data import seed

# Import models so they register on Base.metadata before create_all runs.
from app.models import (  # noqa: F401
    authorization,
    historical_archive,
    ledger_account,
    processed_webhook_event,
    research_record,
    settlement,
    transaction,
    user,
)


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = TestSessionLocal()
    try:
        seed(db)
    finally:
        db.close()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
