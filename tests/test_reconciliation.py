import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base
from app.database.seed_data import seed
from app.models import historical_archive, ledger_account, research_record, transaction, user  # noqa: F401
from app.models.ledger_account import LedgerAccount
from app.services.reconciliation_service import reconcile_all


def test_reconciliation_endpoint_is_clean_immediately_after_seeding(client):
    response = client.get("/reconciliation")
    assert response.status_code == 200
    report = response.json()
    assert report["discrepancies"] == []
    assert report["accounts_checked"] >= 4  # platform, archive, transcriptionist, researcher


def test_reconciliation_endpoint_stays_clean_after_a_real_purchase(client):
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    record = client.get("/records").json()[0]
    client.post("/purchase", json={"research_record_id": record["id"], "user_id": researcher["id"]})

    response = client.get("/reconciliation")
    assert response.json()["discrepancies"] == []


def test_reconciliation_requires_api_key(client):
    client.headers.pop("X-API-Key", None)
    response = client.get("/reconciliation")
    assert response.status_code == 401


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    seed(session)
    yield session
    session.close()


def test_reconciliation_detects_a_balance_corrupted_outside_the_service_layer(db_session):
    account = db_session.query(LedgerAccount).first()

    # Bypass adjust_balance entirely — simulates a bug, a bad manual fix, or
    # anything else that could leave balance_cents out of sync with reality.
    db_session.execute(
        update(LedgerAccount).where(LedgerAccount.id == account.id).values(balance_cents=99_999)
    )
    db_session.commit()

    report = reconcile_all(db_session)

    assert not report.is_clean
    bad = next(d for d in report.discrepancies if d.ledger_account_id == account.id)
    assert bad.stored_balance_cents == 99_999
    assert bad.computed_balance_cents == 0  # no transactions were ever posted
    assert bad.drift_cents == 99_999
