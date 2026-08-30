def test_accounts_are_seeded_with_balances(client):
    response = client.get("/accounts")
    assert response.status_code == 200
    accounts = response.json()
    assert len(accounts) >= 3
    assert {a["owner_type"] for a in accounts} >= {"archive", "user", "platform"}


def test_ledger_is_empty_before_any_purchase(client):
    response = client.get("/ledger")
    assert response.status_code == 200
    assert response.json() == []


def test_ledger_reflects_settled_transactions_after_purchase(client):
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    record = client.get("/records").json()[0]

    client.post(
        "/purchase", json={"research_record_id": record["id"], "user_id": researcher["id"]}
    )

    response = client.get("/ledger")
    transactions = response.json()
    assert len(transactions) == 4
    assert all(t["status"] == "posted" for t in transactions)
    debit_total = sum(t["amount_cents"] for t in transactions if t["type"] == "debit")
    credit_total = sum(t["amount_cents"] for t in transactions if t["type"] == "credit")
    assert debit_total == credit_total == record["price_cents"]
