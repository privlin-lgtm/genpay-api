# GenPay-API

[![CI](https://github.com/privlin-lgtm/genpay-api/actions/workflows/ci.yml/badge.svg)](https://github.com/privlin-lgtm/genpay-api/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688)
![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0-red)

A Banking-as-a-Service platform, built to be architecturally honest about what a
real payment system has to get right: an auditable double-entry ledger, an
asynchronous multi-stage card-authorization flow, signed and idempotent webhooks,
and revenue-splitting math that's proven — not just assumed — to never lose a cent
to rounding.

The business scenario is a genealogy records marketplace (a researcher buys access
to a digitized census record; proceeds split between the archive, the
transcriptionist, and the platform), but the scenario is a vehicle. The engineering
underneath it is the point.

## Contents

- [Why this exists](#why-this-exists)
- [Architecture](#architecture)
- [Core concepts](#core-concepts)
- [API walkthrough](#api-walkthrough)
- [Testing strategy](#testing-strategy)
- [Getting started](#getting-started)
- [Project structure](#project-structure)

## Why this exists

Most portfolio payment projects stop at "charge a card, write a row." This one is
built around the parts of a real BaaS platform that are easy to skip and expensive
to skip in production:

| Concern | What most demos do | What this does |
|---|---|---|
| Ledger correctness | Add/subtract a balance column | Double-entry postings; balance updates are a single atomic SQL `UPDATE`, not a read-modify-write (see [Incident #2](docs/incidents.md#2-lost-update-race-on-ledgeraccountbalance_cents)) |
| Revenue splitting | `round(total * pct)` per party | Integer basis-point math + largest-remainder allocation — provably sums to the total for every input, not just the ones that divide evenly |
| Webhook trust | Accept whatever arrives | HMAC-SHA256 signature verification with a timestamp-tolerance window (Stripe-style) |
| Retry safety | Hope the client doesn't double-click | Idempotency keys claimed *before* processing, not after — closes the exact race window a naive implementation leaves open |
| Transaction integrity | Commit after every write | One transaction per request; a failure anywhere rolls back everything, so the ledger can't be left half-posted |
| Schema evolution | `create_all()` and hope | Alembic migrations, verified against the models in CI |
| "Does it work on Postgres?" | Untested assumption | A real Postgres 16 service container runs the full suite in CI |

Full write-up of the bugs that shaped these decisions — including one where the
ORM's own identity map made a broken transaction look fixed when it wasn't — is in
[docs/incidents.md](docs/incidents.md).

## Architecture

```mermaid
flowchart TB
    subgraph Client["Client / Card Processor"]
        C1[Researcher purchase request]
        C2[Simulated card processor webhooks]
    end

    subgraph API["FastAPI — app/api/"]
        Auth["X-API-Key auth<br/>(internal routes)"]
        Sig["HMAC signature verify<br/>(processor webhooks)"]
        Idem["Idempotency-Key claim<br/>(before processing)"]
    end

    subgraph Services["app/services/ — business logic"]
        Payment[payment_service<br/>authorize → settle]
        Split[revenue_split<br/>basis-point + largest-remainder]
        Ledger[ledger_service<br/>balanced entry posting]
        Processor[processor_event_service<br/>webhook state machine]
    end

    subgraph Repos["app/repositories/ — the only DB-touching layer"]
        R1[(one module per entity)]
    end

    subgraph DB["PostgreSQL / SQLite"]
        Users[(users)]
        Ledger_T[(ledger_accounts)]
        Auth_T[(authorizations)]
        Settle_T[(settlements)]
        Txn[(transactions)]
    end

    C1 --> Auth --> Idem --> Payment
    C2 --> Sig --> Processor --> Payment
    Payment --> Split
    Payment --> Ledger
    Ledger --> R1
    Payment --> R1
    Processor --> R1
    R1 --> DB
```

Every write goes through exactly one transaction, committed once at the end of the
request ([`get_db()`](app/database/db.py)) — not once per repository call. A
failure anywhere in a purchase rolls back the whole thing, so there's no window
where a `Settlement` exists with only some of its `Transaction` postings written.

### Authorization lifecycle

The realistic path (`POST /webhooks/processor-events`) models a card authorization
as a state machine, not a single atomic action — the same shape a real issuer
integration has:

```mermaid
stateDiagram-v2
    [*] --> pending: authorization.created
    pending --> authorized: authorization.approved
    pending --> declined: authorization.declined
    authorized --> settled: settlement.completed<br/>(ledger posted)
    declined --> [*]
    settled --> [*]
```

A simplified synchronous path (`POST /purchase`) also exists for quick
demonstration — it authorizes and settles in one call, skipping the separate
approval step. Both converge on the same `payment_service.settle_authorization`,
so the revenue-split and ledger-posting logic is never duplicated.

## Core concepts

### Double-entry ledger accounting

Every `LedgerAccount` (one per user, one per archive, one platform account) is
credited and debited through `Transaction` rows tied to a `Settlement`. Balances
are never set directly — they're the sum of posted transactions, kept in sync via
an atomic `balance = balance + delta` `UPDATE`. `ledger_service.post_entries`
refuses to post a set of entries where debits don't equal credits.

### Revenue sharing

70% archive / 20% transcriptionist / 10% platform by default, configurable via env
vars (`ARCHIVE_SHARE_BPS`, etc. — see [`app/services/revenue_split.py`](app/services/revenue_split.py)).
The split uses integer basis-point math (never floats) and the largest-remainder
method, so `archive_cents + transcriptionist_cents + platform_cents` equals the
total exactly, for every possible amount — proven with a parametrized sweep across
14 amounts in [`tests/test_revenue_split.py`](tests/test_revenue_split.py), plus a
test demonstrating the naive `round(total * pct)` approach actually loses a cent at
`total_cents = 2`.

### Webhook architecture

`POST /webhooks/processor-events` receives a Stripe-shaped event envelope
(`event_id`, `event_type`, `occurred_at`, `data`) covering
`authorization.created` / `.approved` / `.declined` / `settlement.completed`.
Every request:
1. Verifies `X-GenPay-Signature: t=<unix_ts>,v1=<hmac-sha256>` in constant time,
   rejecting anything older than 5 minutes (replay protection).
2. Claims `event_id` via an atomic insert *before* running the handler — the
   insert's own unique-constraint failure is the concurrency guard, not a
   separate check-then-act that leaves a race window.
3. Runs the handler inside the same transaction that claim lives in, so a failed
   attempt doesn't permanently burn the `event_id` for a corrected retry.

### Banking-as-a-Service concepts modeled

- **Ledger accounts provisioned automatically** on entity creation (a `User` or
  `HistoricalArchive` gets its `LedgerAccount` in the same call that creates it)
- **Authorize/settle separation**, matching how card networks actually hold funds
  before capturing them
- **Idempotent mutation endpoints** — `POST /purchase` requires an
  `Idempotency-Key`; retrying a timed-out request returns the original result
  instead of creating a second purchase
- **Auditability** — `Authorization` → `Settlement` → `Transaction` rows are never
  deleted or mutated after posting

## API walkthrough

Interactive docs (Swagger UI) run at `/docs` once the server is up:

![Swagger UI endpoint overview](docs/screenshots/swagger-overview.png)

Every mutating and financial endpoint documents its own contracts inline — here's
`POST /purchase`, showing the required `Idempotency-Key` and `x-api-key` headers:

![POST /purchase expanded, showing required headers](docs/screenshots/swagger-purchase-endpoint.png)

### Example: buy access to a record

```bash
curl -X POST http://127.0.0.1:8000/purchase \
  -H "x-api-key: change-me" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "research_record_id": "ce8f1e85-c5a3-4c40-a5ca-fe9331049132",
    "user_id": "7dfb10f1-b7b1-42bb-964a-c9c9ddd3a456"
  }'
```

Real executed response, captured directly from a running instance — a $5.99
purchase split into an $4.19 archive credit, $1.20 transcriptionist credit, and
$0.60 platform credit, four balanced ledger postings, no rounding gap:

![POST /purchase executed, showing the real 200 response with revenue split](docs/screenshots/swagger-purchase-executed.png)

### Example: simulated card-processor webhook

```bash
BODY='{"event_type":"card_authorization","amount":5.99,"record_id":"CENSUS-1880-004"}'
SECRET="change-me"
TS=$(date +%s)
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)

curl -X POST http://127.0.0.1:8000/webhooks/card-auth \
  -H "Content-Type: application/json" \
  -H "X-GenPay-Signature: t=$TS,v1=$SIG" \
  -d "$BODY"
```

Full endpoint reference, request/response shapes, and error codes:
[docs/api-spec.md](docs/api-spec.md). Design rationale and diagrams:
[docs/architecture.md](docs/architecture.md),
[docs/payment-flow.md](docs/payment-flow.md).

## Testing strategy

**70 tests**, organized by what they're actually proving rather than by file
mechanics:

| Category | What it proves | Example |
|---|---|---|
| Unit — pure logic | `revenue_split` needs zero DB or HTTP to test | Parametrized sweep across 14 amounts confirming the split always sums to the total |
| Integration — API | End-to-end request/response contracts | A real `POST /purchase` produces exactly 4 posted transactions summing to the price |
| Regression | A specific bug can't come back silently | The lost-update balance race, the SAVEPOINT/rollback finding, retry-after-failure for both idempotency mechanisms |
| Security | Auth and signature verification actually gate what they claim to | Missing/wrong API key, missing/invalid/stale webhook signature, all independently tested |
| Concurrency-adjacent | Two sessions, simulating what one connection pool would see | `test_adjust_balance_reflects_a_concurrent_writers_change_not_a_stale_read` |

The same suite runs against **both SQLite and a real PostgreSQL 16 service
container** in CI — not because SQLite is wrong for local dev, but because two of
the fixes above (the atomic balance `UPDATE`, the idempotency claim's transaction
behavior) were reasoned about in terms of Postgres semantics that SQLite's
single-writer locking doesn't exercise the same way. "The tests pass" means that on
both, not just the one that's convenient to run locally.

```bash
pytest                    # 70 tests, in-memory SQLite, ~1.5s
ruff check app/ tests/ alembic/
mypy app/
```

## Getting Started

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The app seeds demo data on startup: one archive, one transcriptionist, one
researcher, and one purchasable record (`CENSUS-1880-004`, $5.99). Every internal
route needs `x-api-key: change-me` (the dev default); catalog browsing
(`GET /records`, `GET /archives`) is public.

### Database Migrations

```bash
alembic upgrade head                              # apply all migrations
alembic revision --autogenerate -m "description"  # generate a new one after model changes
alembic check                                      # verify models match the latest migration (used in CI)
```

### Testing against Postgres locally

```bash
docker compose up -d
TEST_DATABASE_URL=postgresql+psycopg://genpay:genpay@localhost:5432/genpay pytest
```

## Project structure

```
app/
├── api/            # HTTP boundary: routing, auth, request/response shape
├── schemas/        # Pydantic I/O contracts, decoupled from the ORM
├── services/        # business logic — revenue split, ledger posting, webhook dispatch
├── repositories/    # the only layer that touches a DB session
├── models/          # SQLAlchemy ORM models
├── security/         # webhook signature verification
└── database/        # engine/session setup, seed data

alembic/              # schema migrations
tests/                 # 70 tests: unit, integration, regression, security
docs/                  # architecture, API spec, payment flow, engineering journal
```

Layering is enforced by convention, not by a framework: `api` never imports
`repositories` directly, `services` never construct raw SQL. See
[docs/architecture.md](docs/architecture.md) for the reasoning behind each layer.
