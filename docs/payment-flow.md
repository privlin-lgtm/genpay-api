# Payment Flow

Narrated walkthrough of a single purchase, tracing which code runs at each step.
See [architecture.md](architecture.md#5-payment-lifecycle) for the entity-level
diagram this expands on.

## Trigger: either path lands in the same place

- **Direct purchase** — a client calls `POST /purchase` with a `research_record_id`
  and `user_id`. Handled by [`app/api/payments.py`](../app/api/payments.py), which
  calls `payment_service.purchase_record` directly.
- **Simulated card processor** — an external system (or a test script) calls
  `POST /webhooks/card-auth` with `{event_type, amount, record_id}`. Handled by
  [`app/api/webhooks.py`](../app/api/webhooks.py) → `settlement_service.handle_card_authorization`,
  which resolves `record_id` (a human-facing reference like `CENSUS-1880-004`) to a
  `ResearchRecord`, picks a researcher if `user_id` wasn't given, converts the
  dollar `amount` to cents, and then calls the *same* `payment_service.purchase_record`.

Both paths converge on [`app/services/payment_service.py`](../app/services/payment_service.py).

## Inside `purchase_record`

1. **Look up the record and the researcher.** Missing either raises `ValueError`
   (surfaced as HTTP 400) before anything is written.
2. **Compute the split** off the total: 70% archive, 20% transcriptionist, 10%
   platform, with the platform absorbing rounding remainder and the
   transcriptionist's share if the record has none assigned.
3. **Resolve the three (or four) `LedgerAccount`s involved** — researcher's,
   archive's, transcriptionist's (if any), platform's. If the researcher, archive,
   or platform account is missing, this raises before any row is written — no
   partial state.
4. **Create the `Authorization`** row (status `authorized`) — this is the record of
   "a charge was approved for this amount, for this record, by this user."
5. **Create the `Settlement`** row linked to that authorization (status `settled`)
   — this is what actually triggers money movement.
6. **Call `ledger_service.post_entries`** with a list of `LedgerEntry(account, type,
   amount)` — one debit (researcher, full amount) and up to three credits (archive,
   transcriptionist, platform). `post_entries` first asserts debits == credits, then
   for each entry: inserts a `Transaction` row already in `posted` status, and
   applies the delta to that account's `balance_cents` in the same step.
7. **Return a `PurchaseResult`** — both IDs, both statuses, the split breakdown, and
   the four `TransactionRead` rows, so the caller can see exactly what moved.

## Why authorize-then-settle instead of one step

Real card networks separate authorization (funds are held) from settlement (funds
actually move), often by hours or days, and authorizations can expire or be
declined without ever settling. Modeling that split here — even though this demo
settles immediately — is what makes the `Authorization`/`Settlement` distinction
meaningful rather than decorative, and is the natural extension point for adding
a real delay, a `POST /settlements` trigger, or expiry handling later.

## Failure behavior

Every failure in this path is a `ValueError` caught at the API layer and returned
as `400` with the message as `detail` — an unknown record, an unknown user, a
missing ledger account, or (inside `ledger_service.post_entries`) an unbalanced
entry set. In every case, nothing is written to the database before the failure —
there's no cleanup step because there's nothing to clean up.
