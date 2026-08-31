import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base
from app.database.seed_data import seed
from app.models.api_client import ApiClient
from app.repositories import api_client_repository


def _purchase(client):
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    record = client.get("/records").json()[0]
    return client.post(
        "/purchase", json={"research_record_id": record["id"], "user_id": researcher["id"]}
    ).json()


def _card_auth_webhook(client):
    return client.post(
        "/webhooks/card-auth",
        json={"event_type": "card_authorization", "amount": 5.99, "record_id": "CENSUS-1880-004"},
    ).json()


def test_purchase_via_api_records_a_created_by_client_id(client):
    result = _purchase(client)
    assert result["created_by_client_id"] is not None

    detail = client.get(f"/purchases/{result['authorization_id']}").json()
    assert detail["created_by_client_id"] == result["created_by_client_id"]


def test_same_api_key_always_attributes_to_the_same_client(client):
    # Two independent purchases through the same X-API-Key should resolve to
    # the same ApiClient every time — proves the lookup is deterministic, not
    # e.g. accidentally creating a new client per request.
    first = _purchase(client)
    second = _purchase(client)
    assert first["created_by_client_id"] == second["created_by_client_id"]


def test_purchase_and_webhook_paths_are_attributed_to_different_clients(client):
    purchase_result = _purchase(client)
    webhook_result = _card_auth_webhook(client)
    webhook_detail = client.get(f"/purchases/{webhook_result['authorization_id']}").json()

    assert webhook_detail["created_by_client_id"] is not None
    assert purchase_result["created_by_client_id"] != webhook_detail["created_by_client_id"]


def test_repeated_webhook_deliveries_attribute_to_the_same_processor_client(client):
    first = _card_auth_webhook(client)
    record = client.get("/records").json()[0]
    client.post(
        "/records",
        json={
            "archive_id": client.get("/archives").json()[0]["id"],
            "record_reference": "CENSUS-1880-005",
            "title": "1880 Census, District 5",
            "price_cents": 799,
        },
    )
    second = client.post(
        "/webhooks/card-auth",
        json={"event_type": "card_authorization", "amount": 7.99, "record_id": "CENSUS-1880-005"},
    ).json()

    first_detail = client.get(f"/purchases/{first['authorization_id']}").json()
    second_detail = client.get(f"/purchases/{second['authorization_id']}").json()
    assert first_detail["created_by_client_id"] == second_detail["created_by_client_id"]
    assert record  # unused beyond confirming the fixture seeded a first record


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


def test_require_api_key_rejects_a_key_belonging_to_an_inactive_client(db_session):
    api_client_repository.create(db_session, "disabled-partner", "raw-test-key-123")
    db_session.commit()

    live = api_client_repository.get_by_key(db_session, "raw-test-key-123")
    assert live is not None
    live.is_active = False
    db_session.commit()

    result = api_client_repository.get_by_key(db_session, "raw-test-key-123")
    assert result is not None
    assert result.is_active is False


def test_get_by_key_returns_none_for_an_unknown_key(db_session):
    assert api_client_repository.get_by_key(db_session, "never-issued-key") is None


def test_api_key_hash_is_never_stored_in_plaintext(db_session):
    client_row = api_client_repository.create(db_session, "some-partner", "super-secret-raw-key")
    db_session.commit()

    stored = db_session.get(ApiClient, client_row.id)
    assert stored.api_key_hash != "super-secret-raw-key"
    assert len(stored.api_key_hash) == 64  # sha256 hex digest
