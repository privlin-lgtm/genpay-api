# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

GenPay-API is a FastAPI Banking-as-a-Service backend built around a genealogy
records marketplace (researchers buy access to digitized census records;
proceeds split between an archive, a transcriptionist, and the platform). The
scenario is a vehicle — the actual point is getting the hard parts of a real
payment system right: a double-entry ledger, an async multi-stage card-auth
state machine, signed/idempotent webhooks, and revenue-split math proven to
never lose a cent to rounding.

Background on why specific design decisions were made — including bugs found
along the way — is in [docs/incidents.md](docs/incidents.md),
[docs/architecture.md](docs/architecture.md), and
[docs/payment-flow.md](docs/payment-flow.md). Full endpoint reference:
[docs/api-spec.md](docs/api-spec.md).

## Commands

```bash
# Setup
python -m venv .venv
.venv/Scripts/activate            # Windows; `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt   # runtime deps
pip install -r requirements-dev.txt  # + ruff, mypy, etc. for lint/type-check

# Run the app (seeds demo data on startup)
uvicorn app.main:app --reload

# Tests
pytest                              # 87 tests, in-memory SQLite, ~2s
pytest -v
pytest tests/test_revenue_split.py  # single file
pytest tests/test_revenue_split.py::test_name  # single test

# Lint / type-check (both run in CI)
ruff check app/ tests/ alembic/
mypy app/

# Migrations
alembic upgrade head                              # apply all migrations
alembic revision --autogenerate -m "description"  # generate one after model changes
alembic check                                      # verify models match latest migration (CI gate)

# Test against real Postgres locally (CI also runs the full suite against Postgres 16)
docker compose up -d
TEST_DATABASE_URL=postgresql+psycopg://genpay:genpay@localhost:5433/genpay pytest
```

Every internal route requires `x-api-key: change-me` (dev default, resolved
via `app/api/deps.py::require_api_key`); `GET /records` and `GET /archives`
are the only public routes. Interactive docs at `/docs` once running.

## Architecture

Strict layering, enforced by convention (not a framework):
`app/api/` → `app/services/` → `app/repositories/` → DB. `api` never imports
`repositories` directly; `services` never construct raw SQL.

```
app/
├── api/            # HTTP boundary: routing, auth (require_api_key), request/response shape
├── schemas/        # Pydantic I/O contracts, decoupled from the ORM
├── services/        # business logic: revenue split, ledger posting, webhook dispatch
├── repositories/    # the ONLY layer that touches a DB session — one module per entity
├── models/          # SQLAlchemy ORM models
├── security/         # webhook HMAC signature verification
└── database/        # engine/session setup (db.py), seed data (seed_data.py)

alembic/    # schema migrations
tests/      # unit, integration, regression, security — see conftest.py fixture below
docs/       # architecture, API spec, payment flow, incident write-ups
scripts/    # reconcile.py (ledger reconciliation), capture_screenshots.py
```

### Transaction boundary

`app/database/db.py::get_db()` is the **only** place that commits — one
transaction per request. Repositories only call `flush()`, never `commit()`.
Any exception anywhere during a request (including a deliberate
`HTTPException`) rolls back everything written so far, so a purchase or
ledger posting can never be left half-applied. Keep this pattern when adding
new write paths: services/repositories flush, `get_db()` commits.

### Double-entry ledger

Every `LedgerAccount` (one per user, one per archive, one platform account)
is only ever touched through `Transaction` rows tied to a `Settlement`.
Balances are never set directly — `ledger_account_repository` updates them
via a single atomic `balance = balance + delta` SQL `UPDATE` (not a
read-modify-write) to avoid a lost-update race under concurrent writers.
`ledger_service.post_entries` refuses to post any set of entries where debits
don't equal credits.

### Revenue split (`app/services/revenue_split.py`)

70% archive / 20% transcriptionist / 10% platform by default, in basis
points via `ARCHIVE_SHARE_BPS` / `TRANSCRIPTIONIST_SHARE_BPS` /
`PLATFORM_SHARE_BPS` (must sum to 10000). Uses integer basis-point math plus
the largest-remainder method — never floats — so the three shares always sum
exactly to the total, including cent amounts that don't divide evenly. If you
touch this file, keep the parametrized sweep in
`tests/test_revenue_split.py` passing across all amounts, not just typical
ones.

### Authorization lifecycle / webhooks

`POST /webhooks/processor-events` models card authorization as a state
machine (`pending → authorized/declined → settled`), the same shape a real
issuer integration has. `POST /purchase` is a simplified synchronous path
that authorizes and settles in one call; both converge on
`payment_service.settle_authorization` so revenue-split/ledger logic is never
duplicated.

Every webhook request:
1. Verifies `X-GenPay-Signature: t=<unix_ts>,v1=<hmac-sha256>` in constant
   time via `app/security/webhook_signature.py`, rejecting anything older
   than 5 minutes.
2. Claims `event_id` via an atomic insert *before* running the handler — the
   insert's unique-constraint failure is the concurrency guard, not a
   separate check-then-act.
3. Runs the handler inside the same transaction the claim lives in, so a
   failed attempt doesn't permanently burn the `event_id` for a retry.

`POST /purchase` similarly requires an `Idempotency-Key` header, claimed
before processing (same before-not-after pattern), so a retried request
returns the original result instead of creating a duplicate purchase.

### Auth

`require_api_key` (`app/api/deps.py`) looks up the caller by key hash (not a
single shared secret compared directly), returning the resolved `ApiClient`
so routes can stamp an actor (e.g. `Authorization.created_by_client_id`). A
missing key returns 401, not FastAPI's default 422, since a missing key is
an auth failure, not a malformed request. Two `ApiClient`s are seeded:
`internal-admin` (key = `INTERNAL_API_KEY`, i.e. `change-me` in dev — every
existing curl example/test still works unchanged) and `processor-webhook`, a
system actor attributed to authorizations created via the signed webhook
path (which never has an X-API-Key of its own to look up).

### Refunds

`payment_service.refund_settlement` fully reverses a settled purchase: posts
a new transaction set with each original entry's type flipped (same account,
same amount), which nets every affected balance back to pre-purchase. The
*original* transactions are never mutated — only flagged
`TransactionStatus.reversed` for display — so the ledger stays append-only;
what actually undoes the balance is the new offsetting entries, not a change
to history. `POST /purchases/{id}/refund` exposes this; unlike `/purchase` it
doesn't need an idempotency key, because the settlement's own state machine
(`settled -> reversed`) already makes a retry return 400 instead of
double-refunding.

### Reconciliation

`app/services/reconciliation_service.py::reconcile_all` independently
verifies every `LedgerAccount.balance_cents` still equals the sum of its
transaction history — the invariant `adjust_balance`'s atomic `UPDATE` is
supposed to guarantee at write time, checked again after the fact. Both
`posted` and `reversed` transactions count toward the sum (both had their
effect actually applied via `adjust_balance` when created — `reversed` is a
display flag, not an exclusion); only get right that this includes `reversed`
rows if you touch this function, or a refund will silently show up as a false
discrepancy. Exposed via `GET /reconciliation` and `scripts/reconcile.py`
(the latter for cron/scheduled use — see `.github/workflows/reconciliation.yml`
for a runnable example, honestly scoped since this project has no deployed
persistent DB to actually monitor).

### Startup behavior (`app/main.py`)

`Base.metadata.create_all()` runs on startup as a dev convenience so
`uvicorn app.main:app` works with zero setup; it's a no-op against a DB
already at the current schema and cannot express renames/backfills/constraint
changes — real deployments should run `alembic upgrade head` as an explicit
step instead. Startup also refuses to boot in `ENV=production` if any secret
(`SECRET_KEY`, `WEBHOOK_SIGNING_SECRET`, `INTERNAL_API_KEY`) is still the
`change-me` default.

## Testing conventions

- `tests/conftest.py`'s `client` fixture spins up an isolated DB per test
  (in-memory SQLite by default; set `TEST_DATABASE_URL` to point it at
  Postgres instead — CI runs the full suite against both). It seeds demo
  data and pre-sets `X-API-Key` / `Idempotency-Key` headers on the returned
  `TestClient`.
- The suite runs against SQLite *and* a real Postgres 16 CI service
  container on purpose: the atomic-balance `UPDATE` and the idempotency
  claim's transaction behavior were reasoned about in terms of Postgres
  semantics that SQLite's single-writer locking doesn't exercise the same
  way. Don't treat "passes on SQLite" as sufficient for changes touching
  concurrency, locking, or the idempotency/webhook-claim paths.
- Tests are organized by what they prove (unit/pure-logic, integration,
  regression-for-a-specific-past-bug, security, concurrency-adjacent), not
  by mirroring file structure 1:1.
