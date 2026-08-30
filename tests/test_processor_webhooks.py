import json
import uuid
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.security.webhook_signature import sign_payload

SECRET = settings.webhook_signing_secret


def _envelope(event_type: str, data: dict, event_id: str | None = None) -> bytes:
    body = {
        "event_id": event_id or f"evt_{uuid.uuid4().hex[:12]}",
        "event_type": event_type,
        "occurred_at": datetime.now(UTC).isoformat(),
        "data": data,
    }
    return json.dumps(body).encode("utf-8")


def _post(client, raw_body: bytes, secret: str = SECRET, timestamp: int | None = None):
    signature = sign_payload(secret, raw_body, timestamp)
    return client.post(
        "/webhooks/processor-events",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-GenPay-Signature": signature},
    )


def _seed_context(client):
    record = client.get("/records").json()[0]
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    return record, researcher


def test_full_lifecycle_authorization_created_approved_settled(client):
    record, researcher = _seed_context(client)
    processor_auth_id = f"auth_{uuid.uuid4().hex[:10]}"

    created = _post(
        client,
        _envelope(
            "authorization.created",
            {
                "authorization_id": processor_auth_id,
                "merchant_reference": {
                    "research_record_id": record["id"],
                    "user_id": researcher["id"],
                },
                "amount_cents": record["price_cents"],
                "currency": "USD",
                "card_last4": "4242",
                "card_network": "visa",
            },
        ),
    )
    assert created.status_code == 200
    assert created.json()["result"]["status"] == "pending"

    approved = _post(
        client,
        _envelope(
            "authorization.approved",
            {
                "authorization_id": processor_auth_id,
                "hold_expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            },
        ),
    )
    assert approved.status_code == 200
    assert approved.json()["result"]["status"] == "authorized"

    settled = _post(
        client,
        _envelope(
            "settlement.completed",
            {
                "settlement_batch_id": f"stl_{uuid.uuid4().hex[:10]}",
                "authorization_ids": [processor_auth_id],
                "total_amount_cents": record["price_cents"],
            },
        ),
    )
    assert settled.status_code == 200
    body = settled.json()["result"]
    assert len(body["settlements"]) == 1
    assert body["settlements"][0]["total_cents"] == record["price_cents"]
    assert len(body["settlements"][0]["transactions"]) == 4

    ledger = client.get("/ledger").json()
    assert len(ledger) == 4
    assert all(t["status"] == "posted" for t in ledger)


def test_authorization_declined_records_reason_and_blocks_settlement(client):
    record, researcher = _seed_context(client)
    processor_auth_id = f"auth_{uuid.uuid4().hex[:10]}"

    _post(
        client,
        _envelope(
            "authorization.created",
            {
                "authorization_id": processor_auth_id,
                "merchant_reference": {"research_record_id": record["id"], "user_id": researcher["id"]},
                "amount_cents": record["price_cents"],
                "card_last4": "0002",
                "card_network": "visa",
            },
        ),
    )

    declined = _post(
        client,
        _envelope(
            "authorization.declined",
            {"authorization_id": processor_auth_id, "decline_reason": "insufficient_funds"},
        ),
    )
    assert declined.status_code == 200
    assert declined.json()["result"]["status"] == "declined"

    settle_attempt = _post(
        client,
        _envelope(
            "settlement.completed",
            {
                "settlement_batch_id": f"stl_{uuid.uuid4().hex[:10]}",
                "authorization_ids": [processor_auth_id],
                "total_amount_cents": record["price_cents"],
            },
        ),
    )
    assert settle_attempt.status_code == 400
    assert "declined" in settle_attempt.json()["detail"]["error"]["message"]


def test_missing_signature_header_is_rejected(client):
    record, researcher = _seed_context(client)
    raw_body = _envelope(
        "authorization.created",
        {
            "authorization_id": "auth_no_sig",
            "merchant_reference": {"research_record_id": record["id"], "user_id": researcher["id"]},
            "amount_cents": 599,
            "card_last4": "4242",
            "card_network": "visa",
        },
    )
    response = client.post(
        "/webhooks/processor-events", content=raw_body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "missing_signature"


def test_invalid_signature_is_rejected(client):
    record, researcher = _seed_context(client)
    raw_body = _envelope(
        "authorization.created",
        {
            "authorization_id": "auth_bad_sig",
            "merchant_reference": {"research_record_id": record["id"], "user_id": researcher["id"]},
            "amount_cents": 599,
            "card_last4": "4242",
            "card_network": "visa",
        },
    )
    response = _post(client, raw_body, secret="wrong-secret")
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "invalid_signature"


def test_stale_timestamp_is_rejected(client):
    record, researcher = _seed_context(client)
    raw_body = _envelope(
        "authorization.created",
        {
            "authorization_id": "auth_stale",
            "merchant_reference": {"research_record_id": record["id"], "user_id": researcher["id"]},
            "amount_cents": 599,
            "card_last4": "4242",
            "card_network": "visa",
        },
    )
    ten_minutes_ago = int(datetime.now(UTC).timestamp()) - 600
    response = _post(client, raw_body, timestamp=ten_minutes_ago)
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "signature_expired"


def test_duplicate_event_id_is_ignored_not_reprocessed(client):
    record, researcher = _seed_context(client)
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    raw_body = _envelope(
        "authorization.created",
        {
            "authorization_id": "auth_dup",
            "merchant_reference": {"research_record_id": record["id"], "user_id": researcher["id"]},
            "amount_cents": 599,
            "card_last4": "4242",
            "card_network": "visa",
        },
        event_id=event_id,
    )

    first = _post(client, raw_body)
    assert first.status_code == 200
    assert first.json()["status"] == "processed"

    second = _post(client, raw_body)
    assert second.status_code == 200
    assert second.json()["status"] == "ignored"

    # Confirms the duplicate delivery didn't create a second Authorization row for
    # the same processor authorization_id: approving it once succeeds cleanly.
    approve_body = _envelope(
        "authorization.approved",
        {
            "authorization_id": "auth_dup",
            "hold_expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
    )
    approved = _post(client, approve_body)
    assert approved.status_code == 200
    assert approved.json()["result"]["status"] == "authorized"


def test_malformed_payload_returns_400(client):
    raw_body = b'{"event_id": "evt_bad", "event_type": "authorization.created", "occurred_at": "2026-01-01T00:00:00Z", "data": {}}'
    response = _post(client, raw_body)
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "event_processing_failed"


def test_unsupported_event_type_returns_400(client):
    raw_body = _envelope("authorization.refunded", {"authorization_id": "auth_x"})
    response = _post(client, raw_body)
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "malformed_payload"


def test_retrying_a_failed_event_id_with_a_corrected_payload_succeeds(client):
    record, researcher = _seed_context(client)
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    processor_auth_id = f"auth_{uuid.uuid4().hex[:10]}"

    # Missing required fields (card_last4, card_network) fails Pydantic
    # validation inside the handler.
    bad_body = _envelope(
        "authorization.created",
        {
            "authorization_id": processor_auth_id,
            "merchant_reference": {"research_record_id": record["id"], "user_id": researcher["id"]},
            "amount_cents": record["price_cents"],
        },
        event_id=event_id,
    )
    failed = _post(client, bad_body)
    assert failed.status_code == 400

    # Same event_id, corrected payload: the failed attempt's claim must not have
    # permanently burned the event_id.
    good_body = _envelope(
        "authorization.created",
        {
            "authorization_id": processor_auth_id,
            "merchant_reference": {"research_record_id": record["id"], "user_id": researcher["id"]},
            "amount_cents": record["price_cents"],
            "card_last4": "4242",
            "card_network": "visa",
        },
        event_id=event_id,
    )
    retried = _post(client, good_body)
    assert retried.status_code == 200
    assert retried.json()["status"] == "processed"


def test_authorization_created_with_unknown_research_record_returns_400(client):
    _, researcher = _seed_context(client)
    raw_body = _envelope(
        "authorization.created",
        {
            "authorization_id": f"auth_{uuid.uuid4().hex[:10]}",
            "merchant_reference": {"research_record_id": "does-not-exist", "user_id": researcher["id"]},
            "amount_cents": 599,
            "card_last4": "4242",
            "card_network": "visa",
        },
    )
    response = _post(client, raw_body)
    assert response.status_code == 400
    assert "Unknown research_record_id" in response.json()["detail"]["error"]["message"]


def test_authorization_created_with_unknown_user_returns_400(client):
    record, _ = _seed_context(client)
    raw_body = _envelope(
        "authorization.created",
        {
            "authorization_id": f"auth_{uuid.uuid4().hex[:10]}",
            "merchant_reference": {"research_record_id": record["id"], "user_id": "does-not-exist"},
            "amount_cents": 599,
            "card_last4": "4242",
            "card_network": "visa",
        },
    )
    response = _post(client, raw_body)
    assert response.status_code == 400
    assert "Unknown user_id" in response.json()["detail"]["error"]["message"]


def test_approving_unknown_authorization_returns_400(client):
    raw_body = _envelope(
        "authorization.approved",
        {
            "authorization_id": "auth_does_not_exist",
            "hold_expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
    )
    response = _post(client, raw_body)
    assert response.status_code == 400
    assert "Unknown authorization_id" in response.json()["detail"]["error"]["message"]
