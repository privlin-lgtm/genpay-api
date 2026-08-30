def test_card_authorization_webhook_settles_a_purchase(client):
    response = client.post(
        "/webhooks/card-auth",
        json={"event_type": "card_authorization", "amount": 5.99, "record_id": "CENSUS-1880-004"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["total_cents"] == 599
    assert len(result["transactions"]) == 4


def test_card_authorization_webhook_rejects_unknown_event_type(client):
    response = client.post(
        "/webhooks/card-auth",
        json={"event_type": "card_refund", "amount": 5.99, "record_id": "CENSUS-1880-004"},
    )
    assert response.status_code == 400


def test_card_authorization_webhook_rejects_unknown_record(client):
    response = client.post(
        "/webhooks/card-auth",
        json={"event_type": "card_authorization", "amount": 5.99, "record_id": "NOPE-0000"},
    )
    assert response.status_code == 400
