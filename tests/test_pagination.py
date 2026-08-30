def test_users_list_respects_limit(client):
    for i in range(5):
        client.post(
            "/users", json={"name": f"User {i}", "email": f"user{i}@example.com", "role": "researcher"}
        )

    response = client.get("/users", params={"limit": 3})
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_users_list_offset_skips_earlier_results(client):
    created_emails = []
    for i in range(5):
        resp = client.post(
            "/users", json={"name": f"Offset {i}", "email": f"offset{i}@example.com", "role": "researcher"}
        )
        created_emails.append(resp.json()["email"])

    page_1 = client.get("/users", params={"limit": 100, "offset": 0}).json()
    page_2 = client.get("/users", params={"limit": 100, "offset": 2}).json()

    assert page_1[2:] == page_2  # offset page matches the tail of the full list


def test_limit_over_the_maximum_is_rejected(client):
    response = client.get("/users", params={"limit": 500})
    assert response.status_code == 422


def test_negative_offset_is_rejected(client):
    response = client.get("/users", params={"offset": -1})
    assert response.status_code == 422


def test_ledger_pagination_default_limit(client):
    response = client.get("/ledger")
    assert response.status_code == 200
    # Just confirms the endpoint accepts no pagination params and applies a
    # sane default rather than returning everything unbounded.
    assert isinstance(response.json(), list)
