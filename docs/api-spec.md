# API Specification

Base URL (local): `http://127.0.0.1:8000`. Interactive OpenAPI docs are served at `/docs`.

All request/response bodies are JSON. Amounts are always integer cents (`amount_cents`,
`price_cents`, `balance_cents`); the one exception is the legacy `/webhooks/card-auth`
payload's `amount` field, which mirrors a real card processor and is a decimal dollar
amount (parsed as `Decimal`, not `float`, to avoid precision loss).

## Authentication

Every endpoint except catalog browsing (`GET /records`, `GET /archives`) and the two
webhook endpoints (which use their own mechanisms — see below) requires an
`X-API-Key` header matching `INTERNAL_API_KEY`. A missing or wrong key returns `401`.
This is a single shared key gating internal/financial routes — not per-caller auth or
role scoping, which a real deployment would want.

## Pagination

Every list endpoint (`GET /users`, `/archives`, `/records`, `/accounts`, `/ledger`)
accepts `limit` (default 50, max 200) and `offset` (default 0) query params.

---

## Users

### `POST /users`
Create a user and provision their `LedgerAccount`.

Request:
```json
{ "name": "Jane Ancestry", "email": "jane@example.com", "role": "researcher" }
```
`role` is one of `researcher`, `transcriptionist`, `platform_admin`.

Response `201`: the created `UserRead` (`id`, `name`, `email`, `role`, `created_at`).

### `GET /users` / `GET /users/{id}`
List all users / fetch one. `404` if not found.

---

## Archives

### `POST /archives`
Request: `{ "name": "...", "description": "...", "owner_user_id": null }`
Creates the archive and its `LedgerAccount` in one step.

### `GET /archives` / `GET /archives/{id}`
List / fetch one. `404` if not found.

---

## Records

### `POST /records`
Request:
```json
{
  "archive_id": "<archive id>",
  "record_reference": "CENSUS-1880-004",
  "title": "1880 Census, District 4",
  "price_cents": 599,
  "transcriptionist_user_id": "<user id or null>"
}
```

### `GET /records` / `GET /records/{id}`
List / fetch one. `404` if not found.

---

## Accounts (ledger accounts)

### `GET /accounts` / `GET /accounts/{id}`
Read-only — accounts are created implicitly by the user/archive services and the
seed script, never directly via the API. Returns `owner_type`, whichever of
`owner_user_id`/`owner_archive_id` applies, `balance_cents`, `currency`, `status`.

---

## Ledger

### `GET /ledger?account_id=<id>`
List transactions, optionally filtered to one ledger account. Each transaction
carries `ledger_account_id`, `settlement_id`, `type` (`debit`/`credit`),
`amount_cents`, `status` (always `posted` once returned — pending/failed states
aren't currently surfaced through this API), and `created_at`.

---

## Payments

### `POST /purchase`
Request: `{ "research_record_id": "<id>", "user_id": "<researcher user id>" }`

Requires an `Idempotency-Key` header (any client-generated unique string). Retrying
with the same key returns the original response instead of creating a second
purchase — needed because a client can never be sure whether a request that timed
out actually landed. A second request with the same key that's still being
processed (or was already claimed) gets `409`. Reusing a key after a request that
*failed* (e.g. unknown record) is fine — the key isn't burned by a failed attempt.

Authorizes and immediately settles the purchase at the record's `price_cents`,
splitting revenue 70/20/10 (archive/transcriptionist/platform — the
transcriptionist's share rolls into platform if the record has none assigned).
Returns a
`PurchaseResult`: `authorization_id`, `settlement_id`, both statuses, the split
breakdown, and the four posted `Transaction` rows.

`400` if the record or user doesn't exist, or if the researcher/archive/platform
ledger accounts are missing.

### `GET /purchases/{authorization_id}`
Returns the `Authorization` row (not the full settlement detail) — status,
amount, `external_reference`, timestamps.

---

## Webhooks

### `POST /webhooks/card-auth`
Simulates an inbound event from a card processor:
```json
{ "event_type": "card_authorization", "amount": 5.99, "record_id": "CENSUS-1880-004" }
```
`record_id` here is the human-facing `record_reference`, not the internal UUID.
`user_id` is optional — if omitted, the first seeded `researcher`-role user is used.

`event_type` must be exactly `"card_authorization"`; anything else is `400`.
On success, behaves identically to `POST /purchase` and returns the same
`PurchaseResult` shape.

### `POST /webhooks/processor-events`
The realistic multi-stage path: authorize → approve/decline → settle, as separate
events instead of one synchronous call. See
[payment-flow.md](payment-flow.md) for the full narrative and
[architecture.md](architecture.md#5-payment-lifecycle) for the state diagram.

Requires an `X-GenPay-Signature: t=<unix_ts>,v1=<hex hmac-sha256>` header (see
`app/security/webhook_signature.py`) — not the `X-API-Key` used elsewhere, since
this endpoint's trust boundary is "the processor," not "an internal caller." A
missing/invalid/stale (>5 min) signature is `401`. Idempotent per `event_id`: a
redelivery returns `{"status": "ignored", ...}` without re-running anything.

Event envelope:
```json
{ "event_id": "evt_...", "event_type": "authorization.created", "occurred_at": "...", "data": { ... } }
```

`event_type` is one of:
- **`authorization.created`** — `data: { authorization_id, merchant_reference: { research_record_id, user_id }, amount_cents, currency, card_last4, card_network }`. Creates a `pending` `Authorization`.
- **`authorization.approved`** — `data: { authorization_id, hold_expires_at }`. `pending` → `authorized`.
- **`authorization.declined`** — `data: { authorization_id, decline_reason }`. `pending` → `declined`.
- **`settlement.completed`** — `data: { settlement_batch_id, authorization_ids: [...], total_amount_cents }`. Settles each listed authorization (must be `authorized`), posting the same 70/20/10 ledger split as `/purchase`.

`400` for an unknown `authorization_id`, an invalid state transition (e.g. approving
an already-declined authorization), or an unknown `research_record_id`/`user_id` in
`authorization.created`'s `merchant_reference`.
