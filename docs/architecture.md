# GenPay-API Architecture

## 1. High-Level Architecture

```
                    ┌─────────────────────┐
                    │   Client / Portal    │
                    │ (researcher UI, or   │
                    │  simulated API call) │
                    └──────────┬───────────┘
                               │ REST
                    ┌──────────▼───────────┐
                    │      FastAPI App      │
                    │  (routing, validation,│
                    │   auth, serialization)│
                    └──────────┬───────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                       │
┌───────▼────────┐  ┌──────────▼─────────┐  ┌──────────▼─────────┐
│ Payment Service │  │  Ledger Service    │  │ Settlement Service  │
│ (purchase logic,│  │ (double-entry      │  │ (webhook intake,    │
│  revenue split) │  │  posting, balances)│  │  event verification)│
└───────┬────────┘  └──────────┬─────────┘  └──────────┬─────────┘
        │                      │                       │
        └──────────────────────┼───────────────────────┘
                                │
                    ┌───────────▼────────────┐
                    │   Persistence Layer     │
                    │ (SQLAlchemy ORM over    │
                    │  SQLite / PostgreSQL)   │
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │   Audit / Event Log     │
                    │ (append-only, immutable)│
                    └─────────────────────────┘

External:  Simulated Card Processor ──POST /webhooks/card-auth──▶ FastAPI App
```

Key architectural principle: **the ledger is the source of truth**. Account balances
are *derived* from settled transactions, never mutated directly — every state change
is a recorded, immutable entry.

## 2. Major Components

| Component | Responsibility |
|---|---|
| **API Layer** (`app/api/`) | HTTP routing, request/response schemas, input validation, HTTP-level error mapping |
| **Repositories** (`app/repositories/`) | The only layer that touches the DB session directly — one module per entity |
| **User / Archive / Record Services** | Entity lifecycle; creating a User or Archive also provisions its `LedgerAccount` |
| **Payment Service** | Orchestrates a purchase: creates the `Authorization` + `Settlement`, computes the revenue split, builds the ledger entries |
| **Ledger Service** | Double-entry bookkeeping primitive — posts a balanced entry set as `Transaction` rows, rejects unbalanced sets, updates account balances |
| **Settlement Service** | Receives simulated card-authorization events, resolves the record + researcher, hands off to Payment Service |
| **Seed/Fixtures** (`app/database/seed_data.py`) | Deterministic demo data — one archive, one transcriptionist, one researcher, one purchasable record, one platform account |

## 3. Database Entities

*(as implemented in `app/models/` — see also the [SQLAlchemy models](../app/models/) themselves)*

```
User
├── id (PK)
├── name
├── email (unique)
├── role              (researcher | transcriptionist | platform_admin)
└── created_at

HistoricalArchive
├── id (PK)
├── name
├── description
├── owner_user_id (FK → User, nullable)
└── created_at

ResearchRecord
├── id (PK)
├── archive_id (FK → HistoricalArchive)
├── record_reference (unique, e.g. "CENSUS-1880-004")
├── title
├── price_cents
├── transcriptionist_user_id (FK → User, nullable)
└── created_at

LedgerAccount
├── id (PK)
├── owner_type            (user | archive | platform)
├── owner_user_id (FK → User, nullable, unique)
├── owner_archive_id (FK → HistoricalArchive, nullable, unique)
│     ← exactly one of these two is set, enforced by a CHECK constraint
│       matching owner_type; both null when owner_type = platform
├── balance_cents          ← derived/cached; source of truth is Transaction sum
├── currency
├── status                 (active | suspended | closed)
└── created_at

ApiClient
├── id (PK)
├── name                        unique, e.g. "internal-admin", "processor-webhook"
├── api_key_hash                sha256 of the raw key — never stored in plaintext
├── is_active
└── created_at

Authorization
├── id (PK)
├── research_record_id (FK → ResearchRecord)
├── user_id (FK → User)        ← the purchasing researcher
├── amount_cents
├── external_reference          simulated card-processor auth ID
├── decline_reason
├── status                     (pending | authorized | declined | expired)
├── created_by_client_id (FK → ApiClient, nullable)  ← who/what initiated this
└── created_at

Settlement
├── id (PK)
├── authorization_id (FK → Authorization, unique)   ← one-to-one
├── settled_amount_cents
├── status                     (settled | failed | reversed)
└── created_at

Transaction (ledger entry)
├── id (PK)
├── ledger_account_id (FK → LedgerAccount)
├── settlement_id (FK → Settlement)
├── type                       (debit | credit)
├── amount_cents
├── currency
├── status                     (pending | posted | reversed)
└── created_at
```

Every `Transaction` set for a given `Settlement` must net to zero (sum of debits =
sum of credits) — enforced in code by `ledger_service.post_entries`, which refuses
to post an unbalanced set — that invariant is what makes it "double-entry."

`LedgerAccount` is provisioned automatically: creating a `User` or `HistoricalArchive`
provisions its ledger account in the same call (`user_service.create_user`,
`archive_service.create_archive`); the platform account is created once at seed time.

## 4. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET`/`POST` | `/users` | List / create users (researcher, transcriptionist, platform_admin) |
| `GET` | `/users/{id}` | User detail |
| `GET`/`POST` | `/archives` | List / create historical archives |
| `GET` | `/archives/{id}` | Archive detail |
| `GET`/`POST` | `/records` | List / create purchasable research records |
| `GET` | `/records/{id}` | Record detail |
| `GET` | `/accounts` | List ledger accounts (with balances) |
| `GET` | `/accounts/{id}` | Ledger account detail |
| `GET` | `/ledger` | List transactions (filterable by `account_id`) |
| `POST` | `/purchase` | Authorize + settle a researcher's purchase of a record; triggers the revenue split |
| `GET` | `/purchases/{authorization_id}` | Purchase (authorization) detail |
| `POST` | `/purchases/{authorization_id}/refund` | Fully reverse a settled purchase — new offsetting entries, originals never mutated |
| `GET` | `/reconciliation` | Re-verify every ledger account's balance against its transaction history |
| `POST` | `/webhooks/card-auth` | Receive a simulated card-authorization event from the "processor" (legacy synchronous path) |
| `POST` | `/webhooks/processor-events` | Realistic async path: `authorization.created`/`.approved`/`.declined`/`settlement.completed`, HMAC-signed |
| `GET` | `/health` | Liveness check |

## 5. Payment Lifecycle

```
1. Researcher calls POST /purchase (or a card-auth webhook arrives at
   POST /webhooks/card-auth, which resolves record_id → ResearchRecord and
   defaults to the first researcher User if none is given)
        │
2. Settlement Service validates the webhook event
   - correct event_type ("card_authorization")
   - record_id resolves to a known ResearchRecord
   - (future) signature/HMAC verification
        │
3. Payment Service creates an Authorization row (status=authorized)
        │
4. Payment Service creates a Settlement row linked to that Authorization
   (status=settled) and computes the revenue split:
   - Archive:          70%
   - Transcriptionist:  20% (rolls into Platform if no transcriptionist is assigned)
   - Platform:          10%
        │
5. Ledger Service posts a balanced entry set (rejects it if debits != credits):
   - Debit  researcher's LedgerAccount     for the full amount
   - Credit archive's LedgerAccount        for its share
   - Credit transcriptionist's LedgerAccount for its share (if any)
   - Credit platform LedgerAccount         for its share
        │
6. Each Transaction is created already "posted"; each LedgerAccount.balance_cents
   updates in the same step
        │
7. PurchaseResult returned: authorization_id, settlement_id, split breakdown,
   and the four Transaction records

All of Authorization, Settlement, and Transaction rows are retained permanently
(audit trail) — nothing is ever deleted or mutated after posting.

Failure paths:
   - Invalid event_type / unknown record_id → 400, nothing is created
   - Missing researcher/archive/platform ledger account → 400, no partial posting
     (Authorization + Settlement are only created after these are confirmed present)
   - (future) Reversal: new offsetting entries, never mutate/delete history
```

## 6. Recommended Technology Stack

| Layer | Choice | Why |
|---|---|---|
| Framework | FastAPI | async, typed, auto OpenAPI docs |
| ORM | SQLAlchemy 2.0 (declarative) | mature, works with both SQLite (dev) and Postgres (prod-like) |
| Validation | Pydantic v2 | request/response schemas, decoupled from ORM models |
| DB (dev) | SQLite | zero-setup for a portfolio project |
| DB (prod-sim) | PostgreSQL | demonstrates real BaaS-grade persistence; swap via `DATABASE_URL` |
| Migrations | Alembic | schema evolution, not just `create_all` (future addition) |
| Testing | Pytest + `TestClient`/`httpx` | endpoint + service-level tests against an in-memory SQLite DB |
| Webhook auth | HMAC signature verification | mirrors real processors (Stripe-style `X-Signature` header) |
| Background settlement (optional) | FastAPI `BackgroundTasks` or a simple queue | demonstrates async settlement vs. synchronous demo path |

## 7. Future Enhancement Ideas

- **Idempotency keys** on `/purchase` and the webhook endpoint (real processors retry deliveries)
- **Reversals/refunds** as offsetting ledger entries rather than deletions
- **Multi-currency support** with an FX-rate table
- **Payout batching** — periodic settlement runs that sweep archive/transcriptionist balances to external bank rails (simulated)
- **Rate limiting + API keys** per researcher/institution
- **Dispute/chargeback simulation** to show incident-response handling
- **Ledger reconciliation job** — nightly check that `sum(transactions)` per account matches cached `balance_cents`
- **Event sourcing view** — rebuild account state purely by replaying `Transaction` history, as a demonstration/test tool
- **OpenTelemetry tracing** across webhook → settlement → ledger, useful for a support engineering / incident-analysis narrative
- **Alembic migrations** for real schema versioning
