def _purchase(client):
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    record = client.get("/records").json()[0]
    result = client.post(
        "/purchase", json={"research_record_id": record["id"], "user_id": researcher["id"]}
    ).json()
    return result, record


def test_full_refund_reverses_every_ledger_entry_back_to_pre_purchase_balances(client):
    accounts_before = {a["id"]: a["balance_cents"] for a in client.get("/accounts").json()}

    result, record = _purchase(client)
    authorization_id = result["authorization_id"]

    refund = client.post(f"/purchases/{authorization_id}/refund", json={"reason": "duplicate charge"})
    assert refund.status_code == 200
    body = refund.json()
    assert body["settlement_status"] == "reversed"
    assert body["refunded_cents"] == record["price_cents"]
    assert body["reason"] == "duplicate charge"
    assert len(body["transactions"]) == 4  # one offsetting entry per original

    accounts_after = {a["id"]: a["balance_cents"] for a in client.get("/accounts").json()}
    assert accounts_after == accounts_before  # net effect is exactly zero


def test_refund_marks_original_transactions_reversed_without_mutating_them(client):
    result, _ = _purchase(client)
    original_transactions = result["transactions"]

    client.post(f"/purchases/{result['authorization_id']}/refund", json={})

    ledger = client.get("/ledger").json()
    for original in original_transactions:
        current = next(t for t in ledger if t["id"] == original["id"])
        assert current["status"] == "reversed"
        assert current["amount_cents"] == original["amount_cents"]  # never mutated
        assert current["type"] == original["type"]  # never mutated


def test_ledger_has_eight_entries_after_a_full_refund_four_original_four_reversal(client):
    result, _ = _purchase(client)
    client.post(f"/purchases/{result['authorization_id']}/refund", json={})

    ledger = client.get("/ledger").json()
    assert len(ledger) == 8
    debit_total = sum(t["amount_cents"] for t in ledger if t["type"] == "debit")
    credit_total = sum(t["amount_cents"] for t in ledger if t["type"] == "credit")
    assert debit_total == credit_total  # still balanced across all 8 rows


def test_refunding_an_already_refunded_settlement_is_rejected(client):
    result, _ = _purchase(client)
    authorization_id = result["authorization_id"]

    first = client.post(f"/purchases/{authorization_id}/refund", json={})
    assert first.status_code == 200

    second = client.post(f"/purchases/{authorization_id}/refund", json={})
    assert second.status_code == 400
    assert "reversed" in second.json()["detail"]


def test_refunding_an_unsettled_authorization_is_rejected(client):
    response = client.post("/purchases/does-not-exist/refund", json={})
    assert response.status_code == 400


def test_refund_reconciles_cleanly(client):
    result, _ = _purchase(client)
    client.post(f"/purchases/{result['authorization_id']}/refund", json={})

    report = client.get("/reconciliation").json()
    assert report["discrepancies"] == []
