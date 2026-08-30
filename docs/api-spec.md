# API Specification

Base URL (local): `http://127.0.0.1:8000`. Interactive OpenAPI docs are served at `/docs`.

All request/response bodies are JSON. Amounts are always integer cents (`amount_cents`,
`price_cents`, `balance_cents`); the one exception is the incoming webhook payload's
`amount` field, which mirrors a real card processor and is a decimal dollar amount.

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
