def test_protected_endpoint_rejects_missing_api_key(client):
    client.headers.pop("X-API-Key", None)
    response = client.get("/accounts")
    assert response.status_code == 401


def test_protected_endpoint_rejects_wrong_api_key(client):
    client.headers["X-API-Key"] = "not-the-right-key"
    response = client.get("/accounts")
    assert response.status_code == 401


def test_protected_endpoint_accepts_correct_api_key(client):
    response = client.get("/accounts")
    assert response.status_code == 200


def test_user_creation_requires_api_key(client):
    client.headers.pop("X-API-Key", None)
    response = client.post("/users", json={"name": "X", "email": "x@example.com", "role": "researcher"})
    assert response.status_code == 401


def test_record_catalog_browsing_is_public_no_api_key_needed(client):
    client.headers.pop("X-API-Key", None)
    response = client.get("/records")
    assert response.status_code == 200


def test_archive_creation_requires_api_key_even_though_listing_is_public(client):
    client.headers.pop("X-API-Key", None)
    get_response = client.get("/archives")
    assert get_response.status_code == 200

    post_response = client.post("/archives", json={"name": "New Archive"})
    assert post_response.status_code == 401
