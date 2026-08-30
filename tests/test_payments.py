def test_purchase_splits_revenue_across_archive_transcriptionist_platform(client):
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    record = client.get("/records").json()[0]

    response = client.post(
        "/purchase", json={"research_record_id": record["id"], "user_id": researcher["id"]}
    )
    assert response.status_code == 200
    result = response.json()

    assert result["total_cents"] == record["price_cents"]
    assert result["archive_cents"] == round(record["price_cents"] * 0.70)
    assert result["transcriptionist_cents"] == round(record["price_cents"] * 0.20)
    assert (
        result["archive_cents"] + result["transcriptionist_cents"] + result["platform_cents"]
        == record["price_cents"]
    )
    assert len(result["transactions"]) == 4


def test_purchase_debits_researcher_and_credits_archive_balance(client):
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    record = client.get("/records").json()[0]
    archive_account_before = next(
        a for a in client.get("/accounts").json() if a["owner_type"] == "archive"
    )

    client.post("/purchase", json={"research_record_id": record["id"], "user_id": researcher["id"]})

    accounts = client.get("/accounts").json()
    researcher_account = next(a for a in accounts if a["owner_user_id"] == researcher["id"])
    archive_account_after = next(a for a in accounts if a["owner_type"] == "archive")

    assert researcher_account["balance_cents"] == -record["price_cents"]
    assert (
        archive_account_after["balance_cents"] - archive_account_before["balance_cents"]
        == round(record["price_cents"] * 0.70)
    )


def test_ten_dollar_purchase_splits_70_20_10_with_exact_ledger_postings(client):
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    archive = client.get("/archives").json()[0]
    transcriptionist = next(u for u in client.get("/users").json() if u["role"] == "transcriptionist")

    record = client.post(
        "/records",
        json={
            "archive_id": archive["id"],
            "record_reference": "CENSUS-1900-010",
            "title": "1900 Census, District 10",
            "price_cents": 1000,  # $10.00
            "transcriptionist_user_id": transcriptionist["id"],
        },
    ).json()

    response = client.post(
        "/purchase", json={"research_record_id": record["id"], "user_id": researcher["id"]}
    )
    assert response.status_code == 200
    result = response.json()

    assert result["total_cents"] == 1000
    assert result["archive_cents"] == 700
    assert result["transcriptionist_cents"] == 200
    assert result["platform_cents"] == 100

    transactions = result["transactions"]
    assert len(transactions) == 4
    debit_total = sum(t["amount_cents"] for t in transactions if t["type"] == "debit")
    credit_total = sum(t["amount_cents"] for t in transactions if t["type"] == "credit")
    assert debit_total == credit_total == 1000
    assert all(t["status"] == "posted" for t in transactions)


def test_purchase_with_unknown_record_returns_400(client):
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")

    response = client.post(
        "/purchase", json={"research_record_id": "does-not-exist", "user_id": researcher["id"]}
    )
    assert response.status_code == 400
