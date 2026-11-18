# MCP server (read-only)

`mcp_server/` exposes GenPay to Claude and other MCP clients as eight
read-only tools. It is a thin HTTP client of the running API: each tool is one
`GET` against a route the API already has, sent with the `mcp-agent` API key.
It never imports `app`, so it can't bypass auth, the
api → services → repositories layering, or `get_db()`'s one-commit-per-request
rule. `tests/test_architecture.py::test_http_only_packages_never_import_app`
fails the build if that ever changes.

Built on the official Python SDK, `mcp==2.3.0` (`MCPServer`, stateless
streamable HTTP).

## Tools

| Tool | Route | Inputs |
|---|---|---|
| `list_records` | `GET /records` | `limit` 1-200 (default 50), `offset` |
| `get_record` | `GET /records/{record_id}` | `record_id` |
| `list_archives` | `GET /archives` | `limit`, `offset` |
| `list_accounts` | `GET /accounts` | `limit`, `offset` |
| `get_account` | `GET /accounts/{account_id}` | `account_id` |
| `list_ledger_transactions` | `GET /ledger` | optional `account_id`, `limit`, `offset` |
| `get_purchase` | `GET /purchases/{authorization_id}` | `authorization_id` |
| `run_reconciliation` | `GET /reconciliation` | none |

Every tool carries `readOnlyHint=true`, `destructiveHint=false`,
`idempotentHint=true`, `openWorldHint=false`, and publishes an output schema.
Money is integer cents, exactly as the API returns it. Inputs are validated
before any HTTP call (`limit=201` never reaches the API).

Not exposed, on purpose: the webhook routes (`/webhooks/*`, the processor's
signed path, not a client action), and every write route. Purchase and refund
tools are planned for a later PR, behind a flag that is off by default.

## Running it

```bash
uvicorn app.main:app                                   # the API, on :8000
GENPAY_MCP_API_KEY=change-me-mcp python -m mcp_server  # MCP over HTTP on 127.0.0.1:8001/mcp
GENPAY_MCP_API_KEY=change-me-mcp python -m mcp_server --stdio   # or over stdio
```

| Env var | Default | |
|---|---|---|
| `GENPAY_MCP_API_KEY` | (required) | The `mcp-agent` client's key; the server refuses to start without it |
| `GENPAY_API_URL` | `http://127.0.0.1:8000` | Where the API runs |
| `GENPAY_MCP_TIMEOUT_SECONDS` | `10` | Per-request timeout to the API |

Add it to Claude Code:

```bash
claude mcp add --transport http genpay http://127.0.0.1:8001/mcp
```

The HTTP transport is stateless (no session kept between requests, so any
instance can serve any call) and keeps the SDK's DNS-rebinding protection: a
request whose `Host` header isn't the server's own is refused with 421.

The MCP endpoint has no authentication of its own yet, so it binds to
127.0.0.1 by default and refuses a non-loopback `--host` unless you pass
`--allow-remote`, which only makes sense behind your own auth proxy.

## Auth

The API seeds a dedicated `mcp-agent` `ApiClient`, keyed by `MCP_AGENT_API_KEY`
(dev default `change-me-mcp`; startup refuses it when `ENV=production`). The
server never holds the `internal-admin` key. A database seeded before this
client existed gets it on the next API startup.

Read-only is enforced twice. The server only registers GET tools, and the API
itself refuses the `mcp-agent` key on any non-GET request with 403
(`READ_ONLY_CLIENT_NAMES` in `app/constants.py`, checked in `require_api_key`).
So a leaked `mcp-agent` key can read the ledger but never write to it.

Rotating `MCP_AGENT_API_KEY` takes effect on the next API startup: the stored
hash is updated and the old key stops working. Startup also refuses to run if
`MCP_AGENT_API_KEY` equals `INTERNAL_API_KEY`.

## Errors

Failures come back to the model as tool errors it can act on: "Record not
found", "GenPay rejected the MCP server's API key; check GENPAY_MCP_API_KEY",
"Could not reach the GenPay API". The API key never appears in an error.

## Tests

`tests/test_mcp_server.py` drives the server through the SDK's own `Client`,
with the suite's `TestClient` as the server's HTTP client, so every call goes
through the real routes, auth and database (SQLite and Postgres in CI). It
covers the tool surface and annotations, each tool's route and parameters,
an end-to-end purchase-to-reconciliation story, the stateless HTTP transport,
error handling, the `mcp-agent` identity, config, seeding and the production
guard.
