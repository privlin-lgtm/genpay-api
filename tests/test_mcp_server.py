"""
The read-only MCP server (mcp_server/), driven through the MCP SDK's own client.

The server's HTTP client is the `client` fixture's TestClient, so every tool
call goes through the real API routes, auth and database (SQLite or Postgres,
like the rest of the suite) with no server process.
"""

import asyncio
from datetime import datetime
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from mcp.client import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult

from app.config import settings
from mcp_server.client import GenPayClient
from mcp_server.config import ConfigError, load_config
from mcp_server.server import build_server

EXPECTED_TOOLS = {
    "list_records",
    "get_record",
    "list_archives",
    "list_accounts",
    "get_account",
    "list_ledger_transactions",
    "get_purchase",
    "run_reconciliation",
}


class Recorder:
    """Records every request the TestClient sends, via an httpx2 event hook."""

    def __init__(self, http: TestClient) -> None:
        self.requests: list[httpx2.Request] = []
        http.event_hooks["request"].append(self.requests.append)


@pytest.fixture()
def recorder(client):
    return Recorder(client)


@pytest.fixture()
def server(client):
    return build_server(GenPayClient(client, settings.mcp_agent_api_key))


def call(server: MCPServer, tool: str, args: dict[str, Any] | None = None) -> CallToolResult:
    async def run() -> CallToolResult:
        async with Client(server) as mcp:
            return await mcp.call_tool(tool, args or {})

    return asyncio.run(run())


def payload(result: CallToolResult) -> Any:
    assert not result.is_error, result.content
    data = result.structured_content
    assert data is not None
    return data["result"] if set(data) == {"result"} else data


def normalize(data: Any) -> Any:
    """Compare API and tool output field by field, with timestamps parsed (their string form can differ)."""
    if isinstance(data, list):
        return [normalize(d) for d in data]
    if isinstance(data, dict):
        return {
            k: (datetime.fromisoformat(v) if k == "created_at" else normalize(v)) for k, v in data.items()
        }
    return data


def seeded_ids(client) -> dict[str, str]:
    record = client.get("/records").json()[0]
    account = client.get("/accounts").json()[0]
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    purchase = client.post(
        "/purchase",
        json={"research_record_id": record["id"], "user_id": researcher["id"]},
        headers={"Idempotency-Key": "mcp-test-purchase"},
    ).json()
    return {"record": record["id"], "account": account["id"], "purchase": purchase["authorization_id"]}


# --- tool surface -----------------------------------------------------------


def test_exposes_exactly_the_read_only_tools(server):
    async def run():
        async with Client(server) as mcp:
            return (await mcp.list_tools()).tools

    tools = asyncio.run(run())
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name
        assert tool.annotations.idempotent_hint is True, tool.name
        assert tool.annotations.open_world_hint is False, tool.name
        assert tool.output_schema is not None, f"{tool.name} has no output schema"
        assert tool.description, tool.name
        # The signed processor path and every write route stay out of reach.
        assert "webhook" not in tool.name and "refund" not in tool.name, tool.name
        assert not tool.name.startswith(("create", "purchase", "prepare", "confirm")), tool.name


# --- each tool hits the right route ------------------------------------------


ROUTES = [
    ("list_records", lambda ids: {"limit": 5, "offset": 0}, "/records", {"limit": "5", "offset": "0"}),
    ("get_record", lambda ids: {"record_id": ids["record"]}, "/records/{record}", {}),
    ("list_archives", lambda ids: {}, "/archives", {"limit": "50", "offset": "0"}),
    ("list_accounts", lambda ids: {"limit": 3}, "/accounts", {"limit": "3", "offset": "0"}),
    ("get_account", lambda ids: {"account_id": ids["account"]}, "/accounts/{account}", {}),
    ("list_ledger_transactions", lambda ids: {}, "/ledger", {"limit": "50", "offset": "0"}),
    (
        "list_ledger_transactions",
        lambda ids: {"account_id": ids["account"]},
        "/ledger",
        {"account_id": "{account}", "limit": "50", "offset": "0"},
    ),
    ("get_purchase", lambda ids: {"authorization_id": ids["purchase"]}, "/purchases/{purchase}", {}),
    ("run_reconciliation", lambda ids: {}, "/reconciliation", {}),
]


@pytest.mark.parametrize(("tool", "make_args", "path", "params"), ROUTES)
def test_tool_maps_to_its_route(client, server, recorder, tool, make_args, path, params):
    ids = seeded_ids(client)
    recorder.requests.clear()

    result = call(server, tool, make_args(ids))

    assert len(recorder.requests) == 1
    sent = recorder.requests[0]
    assert sent.method == "GET"
    assert sent.url.path == path.format(**ids)
    assert dict(sent.url.params) == {k: v.format(**ids) for k, v in params.items()}

    direct = client.get(sent.url.path, params=dict(sent.url.params)).json()
    got = payload(result)
    if tool == "run_reconciliation":
        direct = {**direct, "is_clean": not direct["discrepancies"]}
    assert normalize(got) == normalize(direct)


# --- end to end through the SDK client ---------------------------------------


def test_end_to_end_purchase_shows_up_and_ledger_reconciles(client, server):
    """The demo story through the SDK client: find a purchase, follow its ledger entries, reconcile."""
    ids = seeded_ids(client)

    purchase = payload(call(server, "get_purchase", {"authorization_id": ids["purchase"]}))
    assert purchase["amount_cents"] == 599
    assert purchase["status"] == "authorized"
    assert purchase["created_by_client_id"] is not None

    entries = payload(call(server, "list_ledger_transactions"))
    debits = sum(e["amount_cents"] for e in entries if e["type"] == "debit")
    credits = sum(e["amount_cents"] for e in entries if e["type"] == "credit")
    assert debits == credits == 599

    accounts = payload(call(server, "list_accounts"))
    assert any(a["balance_cents"] != 0 for a in accounts)

    report = payload(call(server, "run_reconciliation"))
    assert report == {"accounts_checked": len(accounts), "discrepancies": [], "is_clean": True}


def test_stateless_http_transport_serves_independent_requests(server):
    app = server.streamable_http_app(stateless_http=True, json_response=True)
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(app, base_url="http://127.0.0.1:8001") as http:
        for request_id in (1, 2):
            response = http.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {}},
            )
            assert response.status_code == 200, response.text
            assert "mcp-session-id" not in {k.lower() for k in response.headers}
            assert {t["name"] for t in response.json()["result"]["tools"]} == EXPECTED_TOOLS


def test_http_transport_rejects_a_foreign_host_header(server):
    """DNS-rebinding protection: a browser page on another origin can't drive a local server."""
    app = server.streamable_http_app(stateless_http=True, json_response=True)
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(app, base_url="http://evil.example") as http:
        response = http.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
    assert response.status_code == 421


# --- errors -----------------------------------------------------------------


def test_unknown_record_is_a_readable_tool_error(server):
    result = call(server, "get_record", {"record_id": "no-such-record"})
    assert result.is_error
    assert "Record not found" in result.content[0].text


@pytest.mark.parametrize("bad_id", ["../accounts", "x?limit=1", "a/b", ""])
def test_ids_cannot_reach_another_route(server, recorder, bad_id):
    result = call(server, "get_record", {"record_id": bad_id})
    assert result.is_error
    assert recorder.requests == []


def test_rejected_key_says_how_to_fix_it_without_leaking_the_key(client):
    bad = build_server(GenPayClient(client, "wrong-key-123"))
    result = call(bad, "list_accounts")
    assert result.is_error
    text = result.content[0].text
    assert "GENPAY_MCP_API_KEY" in text
    assert "wrong-key-123" not in text


@pytest.mark.parametrize("limit", [0, 201])
def test_out_of_range_limit_is_rejected_before_any_http_call(server, recorder, limit):
    result = call(server, "list_records", {"limit": limit})
    assert result.is_error
    assert recorder.requests == []


def test_unreachable_api_is_a_tool_error():
    http = httpx2.Client(base_url="http://127.0.0.1:9", timeout=1)
    result = call(build_server(GenPayClient(http, "k")), "list_records")
    assert result.is_error
    assert "Could not reach the GenPay API" in result.content[0].text


# --- auth -------------------------------------------------------------------


def test_server_authenticates_as_mcp_agent_not_internal_admin(server, recorder):
    payload(call(server, "list_accounts"))
    sent_key = recorder.requests[0].headers["x-api-key"]
    assert sent_key == settings.mcp_agent_api_key
    assert sent_key != settings.internal_api_key


# --- config -----------------------------------------------------------------


def test_missing_api_key_fails_at_startup_with_a_clear_message():
    with pytest.raises(ConfigError, match="GENPAY_MCP_API_KEY"):
        load_config({"GENPAY_API_URL": "http://localhost:8000"})


def test_config_reads_url_and_key_from_env():
    config = load_config({"GENPAY_API_URL": "http://api.local:8000/", "GENPAY_MCP_API_KEY": "k"})
    assert config.api_url == "http://api.local:8000"
    assert config.api_key == "k"


# --- seeding and startup guard -----------------------------------------------


def test_seed_backfills_mcp_agent_on_an_already_seeded_database():
    from sqlalchemy import create_engine, delete
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.constants import MCP_AGENT_CLIENT_NAME
    from app.database.db import Base
    from app.database.seed_data import seed
    from app.models.api_client import ApiClient
    from app.repositories import api_client_repository

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        seed(db)
        db.execute(delete(ApiClient).where(ApiClient.name == MCP_AGENT_CLIENT_NAME))
        db.commit()

        seed(db)  # platform account exists, so the main seed returns early

        agent = api_client_repository.get_by_name(db, MCP_AGENT_CLIENT_NAME)
        assert agent is not None
        assert api_client_repository.get_by_key(db, settings.mcp_agent_api_key) == agent
    finally:
        db.close()
        engine.dispose()


def test_production_refuses_the_default_mcp_agent_key(monkeypatch):
    from app import main

    monkeypatch.setattr(main.settings, "env", "production")
    monkeypatch.setattr(
        main,
        "_DEFAULT_SECRETS",
        {
            "secret_key": "real-secret",
            "webhook_signing_secret": "real-secret",
            "internal_api_key": "real-secret",
            "mcp_agent_api_key": "change-me-mcp",
        },
    )
    with pytest.raises(RuntimeError, match="mcp_agent_api_key"):
        main._check_secrets_are_not_defaults()


def test_production_guard_is_wired_to_the_mcp_agent_setting():
    from app import main

    assert main._DEFAULT_SECRETS["mcp_agent_api_key"] == settings.mcp_agent_api_key


def test_production_accepts_a_real_secret_that_starts_with_change_me(monkeypatch):
    from app import main

    monkeypatch.setattr(main.settings, "env", "production")
    monkeypatch.setattr(main, "_DEFAULT_SECRETS", {"mcp_agent_api_key": "change-me-not-a-default-9f3"})
    main._check_secrets_are_not_defaults()


def test_startup_refuses_mcp_agent_sharing_the_internal_key(monkeypatch):
    from app import main

    monkeypatch.setattr(main.settings, "mcp_agent_api_key", main.settings.internal_api_key)
    with pytest.raises(RuntimeError, match="MCP_AGENT_API_KEY must differ"):
        main._check_api_keys_are_distinct()


def test_rotating_the_mcp_agent_key_retires_the_old_one(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database.db import Base
    from app.database.seed_data import seed
    from app.repositories import api_client_repository

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        seed(db)
        old_key = settings.mcp_agent_api_key
        monkeypatch.setattr(settings, "mcp_agent_api_key", "rotated-key-7c1")

        seed(db)

        assert api_client_repository.get_by_key(db, "rotated-key-7c1") is not None
        assert api_client_repository.get_by_key(db, old_key) is None
    finally:
        db.close()
        engine.dispose()


# --- the API itself keeps mcp-agent read-only ---------------------------------


def test_mcp_agent_key_can_read_but_never_write(client):
    agent = {"X-API-Key": settings.mcp_agent_api_key}
    ids = seeded_ids(client)  # created with internal-admin
    researcher = next(u for u in client.get("/users").json() if u["role"] == "researcher")
    archive_id = client.get("/archives").json()[0]["id"]

    assert client.get("/accounts", headers=agent).status_code == 200
    writes = [
        ("/purchase", {"research_record_id": ids["record"], "user_id": researcher["id"]}),
        (f"/purchases/{ids['purchase']}/refund", None),
        ("/records", {"archive_id": archive_id, "record_reference": "X-1", "title": "X", "price_cents": 100}),
        ("/archives", {"name": "Rogue archive"}),
        ("/users", {"name": "Rogue", "email": "rogue@example.com", "role": "researcher"}),
    ]
    for path, body in writes:
        response = client.post(path, json=body, headers={**agent, "Idempotency-Key": f"agent-{path}"})
        assert response.status_code == 403, (path, response.status_code)
        assert response.json()["detail"] == "This API key is read-only"

    # Nothing was written: the purchase is still unrefunded and reconciliation is clean.
    assert client.get("/reconciliation").json()["discrepancies"] == []
    assert client.get(f"/purchases/{ids['purchase']}").json()["status"] == "authorized"


# --- robustness ---------------------------------------------------------------


def test_non_json_success_body_is_a_readable_tool_error():
    http = httpx2.Client(
        base_url="http://api.local",
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200, text="<html>portal</html>")),
    )
    result = call(build_server(GenPayClient(http, "k")), "list_records")
    assert result.is_error
    assert "isn't JSON" in result.content[0].text


@pytest.mark.parametrize("value", ["10s", "0", "-1"])
def test_bad_timeout_is_a_config_error(value):
    with pytest.raises(ConfigError, match="GENPAY_MCP_TIMEOUT_SECONDS"):
        load_config({"GENPAY_MCP_API_KEY": "k", "GENPAY_MCP_TIMEOUT_SECONDS": value})


def test_http_server_refuses_a_network_host_without_allow_remote(monkeypatch, capsys):
    from mcp_server import __main__ as entry

    monkeypatch.setattr("sys.argv", ["mcp_server", "--host", "0.0.0.0"])
    with pytest.raises(SystemExit):
        entry.main()
    assert "--allow-remote" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("host", "loopback"),
    [("127.0.0.1", True), ("localhost", True), ("::1", True), ("0.0.0.0", False), ("10.0.0.5", False)],
)
def test_loopback_detection(host, loopback):
    from mcp_server.__main__ import _is_loopback

    assert _is_loopback(host) is loopback
