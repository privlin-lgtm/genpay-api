def _purchase(client, idempotency_key: str | None = None, **overrides):
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    record = client.get("/records").json()[0]
    payload = {"research_record_id": record["id"], "user_id": researcher["id"], **overrides}
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    return client.post("/purchase", json=payload, headers=headers), record


def test_purchase_without_idempotency_key_header_is_rejected(client):
    client.headers.pop("Idempotency-Key", None)
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    record = client.get("/records").json()[0]
    response = client.post(
        "/purchase", json={"research_record_id": record["id"], "user_id": researcher["id"]}
    )
    assert response.status_code == 422  # FastAPI's required-header validation


def test_retrying_the_same_idempotency_key_returns_the_original_result_not_a_second_purchase(client):
    first, record = _purchase(client, idempotency_key="retry-key-1")
    assert first.status_code == 200
    first_result = first.json()

    second, _ = _purchase(client, idempotency_key="retry-key-1")
    assert second.status_code == 200
    assert second.json() == first_result  # byte-for-byte the cached response

    # Only one purchase actually happened: exactly 4 ledger transactions exist,
    # not 8.
    ledger = client.get("/ledger").json()
    assert len(ledger) == 4


def test_different_idempotency_keys_allow_separate_purchases(client):
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    archive = client.get("/archives").json()[0]
    record_1 = client.post(
        "/records",
        json={
            "archive_id": archive["id"],
            "record_reference": "REC-A",
            "title": "Record A",
            "price_cents": 500,
        },
    ).json()
    record_2 = client.post(
        "/records",
        json={
            "archive_id": archive["id"],
            "record_reference": "REC-B",
            "title": "Record B",
            "price_cents": 700,
        },
    ).json()

    first = client.post(
        "/purchase",
        json={"research_record_id": record_1["id"], "user_id": researcher["id"]},
        headers={"Idempotency-Key": "key-a"},
    )
    second = client.post(
        "/purchase",
        json={"research_record_id": record_2["id"], "user_id": researcher["id"]},
        headers={"Idempotency-Key": "key-b"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["total_cents"] == 500
    assert second.json()["total_cents"] == 700

    ledger = client.get("/ledger").json()
    # 3 postings each (debit researcher, credit archive, credit platform) since
    # neither record has a transcriptionist assigned.
    assert len(ledger) == 6


def test_reusing_a_key_for_a_failed_request_lets_a_corrected_retry_succeed(client):
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    record = client.get("/records").json()[0]

    failed = client.post(
        "/purchase",
        json={"research_record_id": "does-not-exist", "user_id": researcher["id"]},
        headers={"Idempotency-Key": "recoverable-key"},
    )
    assert failed.status_code == 400

    # The failed attempt's claim rolled back with the rest of that transaction,
    # so the same key can be reused for a request that actually succeeds.
    retried = client.post(
        "/purchase",
        json={"research_record_id": record["id"], "user_id": researcher["id"]},
        headers={"Idempotency-Key": "recoverable-key"},
    )
    assert retried.status_code == 200
