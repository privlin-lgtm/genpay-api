# GenPay-API

A simulated Banking-as-a-Service (BaaS) platform designed for genealogy societies, historical archives, and family research organizations.

GenPay-API demonstrates modern fintech concepts including:

- Double-entry ledger accounting
- Card authorization webhooks
- Transaction settlement flows
- Revenue sharing
- REST API design
- Layered architecture (API → services → repositories → ORM)

## Business Scenario

A genealogy researcher purchases access to a digitized census record.

The platform receives a simulated card authorization event and distributes funds among:

- Historical archive
- Record transcriptionist
- Platform operator

## Technology Stack

- Python
- FastAPI
- SQLAlchemy 2.0
- SQLite (dev) / PostgreSQL-ready
- Pydantic v2
- Pytest

## Features

### Ledger Accounts

Every participant is provisioned a `LedgerAccount` automatically when created:

- Researcher (a `User`)
- Transcriptionist (a `User`)
- Historical Archive
- Platform operator (seeded once)

### Simulated Card Processing

Webhook endpoint receives:

```json
{
  "event_type": "card_authorization",
  "amount": 5.99,
  "record_id": "CENSUS-1880-004"
}
```

### Revenue Splitting

Example:

- Archive: 70%
- Transcriptionist: 20%
- Platform Fee: 10%

(If a record has no assigned transcriptionist, their share rolls into the platform fee.)

### Audit Trail

Every purchase creates an `Authorization` → `Settlement` → a balanced set of `Transaction`
rows. Nothing is ever deleted or mutated after posting.

## API Endpoints

| Method | Endpoint | Description |
|----------|------------|-------------|
| GET/POST | /users | List / create users (researcher, transcriptionist, platform_admin) |
| GET/POST | /archives | List / create historical archives |
| GET/POST | /records | List / create purchasable research records |
| GET | /accounts | List ledger accounts and balances |
| GET | /ledger | View transactions |
| POST | /purchase | Simulate a record purchase |
| GET | /purchases/{id} | Purchase detail |
| POST | /webhooks/card-auth | Receive a simulated card authorization |

Full endpoint and schema details: [docs/architecture.md](docs/architecture.md),
[docs/api-spec.md](docs/api-spec.md).

## Getting Started

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The app seeds demo data on startup: one archive, one transcriptionist, one researcher,
and one purchasable record (`CENSUS-1880-004`, $5.99). Interactive docs are at
`/docs` once the server is running.

## Database Migrations

Schema changes are managed with Alembic rather than relying on `create_all` (which
can only add missing tables, never express a rename, backfill, or constraint change):

```bash
alembic upgrade head                              # apply all migrations
alembic revision --autogenerate -m "description"  # generate a new one after model changes
alembic check                                      # verify models match the latest migration (used in CI)
```

`alembic/env.py` reads `DATABASE_URL` from the same `Settings` object the app uses,
so both stay in sync from one source.

## Testing

```bash
pip install -r requirements-dev.txt
ruff check app/ tests/ alembic/     # lint
mypy app/                            # type-check
pytest                                # 70 tests, in-memory SQLite
```

The same suite also runs against real PostgreSQL in CI (`.github/workflows/ci.yml`),
since a couple of fixes (the atomic ledger-balance UPDATE, the idempotency-claim
SAVEPOINT behavior) are motivated by Postgres semantics that SQLite's much more
forgiving single-writer locking doesn't exercise. To run it locally:

```bash
docker compose up -d
TEST_DATABASE_URL=postgresql+psycopg://genpay:genpay@localhost:5432/genpay pytest
```

## Why This Project Matters

This project combines modern fintech infrastructure with genealogy and historical preservation.

It showcases practical skills relevant to:

- Banking-as-a-Service
- Payments
- Support Engineering
- API Operations
- Incident Analysis
- Financial Systems
