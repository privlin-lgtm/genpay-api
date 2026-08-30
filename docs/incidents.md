# Engineering Journal: Bugs Found and How They Were Proven

Four real bugs were found and fixed while building this project — not hypothetical
"you should probably..." review comments, but issues caught, reproduced, and fixed
with a falsifiable test in each case. This doc is that record: what the symptom was,
what the actual root cause turned out to be, how it was verified (not just asserted),
and what the fix was. Each one links to the test that would fail again if the fix
were reverted.

---

## 1. SQLite `:memory:` gives every new connection a separate, empty database

**Symptom:** The very first version of the test suite failed with
`sqlalchemy.exc.OperationalError: no such table: research_records` — on a table
that had just been created moments earlier in the same test run.

**Root cause:** `create_engine("sqlite:///:memory:")` without a pinned pool gives
each connection checkout a *fresh, separate* in-memory database. `Base.metadata.create_all()`
ran on one connection; the actual test query ran on a different one from the same
pool — a different, empty database that happened to auto-create the same schema on
first use, hence "table doesn't exist" rather than "empty result."

**Verification:** Reproduced directly — created tables on one connection from a
pool without `StaticPool`, queried from a second connection from the same engine,
got zero rows despite the insert having "succeeded." Confirmed the fix (pinning to
one connection) resolves it by rerunning the same script.

**Fix:** [`tests/conftest.py`](../tests/conftest.py) pins the test engine to a
single connection via `poolclass=StaticPool` — the standard, documented pattern for
testing against SQLite `:memory:` with SQLAlchemy.

---

## 2. Lost-update race on `LedgerAccount.balance_cents`

**Symptom:** Flagged in a staff-engineer code review, not by a failing test —
`adjust_balance` did a plain Python read-modify-write:

```python
account = db.get(LedgerAccount, account_id)
account.balance_cents += delta_cents
db.commit()
```

**Root cause:** Two concurrent transactions can both read `balance_cents = 1000`
before either writes back. Both compute their own delta against that same stale
value; whichever commits second silently overwrites the first's update. The
platform account gets credited on every single purchase, so this is exactly the
kind of code path where that race would eventually fire in production.

**Verification:** [`tests/test_ledger_account_repository.py`](../tests/test_ledger_account_repository.py)
reproduces it directly: session A loads and caches an account (balance 0), session
B — a fully independent writer — commits its own +500, then session A calls
`adjust_balance`. The buggy version returns 100 (session A's own delta applied to
its *stale cached* 0, silently discarding B's +500 because `Session.get()` serves
straight from the identity map without re-querying). The fixed version correctly
returns 600.

**Fix:** [`app/repositories/ledger_account_repository.py`](../app/repositories/ledger_account_repository.py)
replaced the read-modify-write with a single atomic SQL statement:
`UPDATE ... SET balance_cents = balance_cents + :delta`. The increment happens
inside the database, which serializes concurrent writers on the same row — there's
no window where a stale read can be written back, because there's no read to begin
with.

---

## 3. `db.begin_nested()` (SAVEPOINT) doesn't reliably survive a later full rollback

This is the one worth reading in full, because the wrong conclusion is easy to
reach here — the ORM's identity map will happily tell you the fix worked when it
didn't.

**Symptom:** A test asserted that reusing an `Idempotency-Key` after a *failed*
request should let a corrected retry succeed (the failed attempt's claim should
roll back with the rest of that request). It failed with `409 Conflict` on the
retry — as if the first, failed attempt's claim had somehow persisted anyway.

**Original design:** Both idempotency mechanisms (`processed_webhook_event_repository`
and `idempotency_key_repository`) claimed a key by wrapping the insert in
`db.begin_nested()` — a SAVEPOINT — specifically so that catching the resulting
`IntegrityError` on a duplicate wouldn't poison the whole session's transaction.
The assumption was: if the *caller's* later processing fails and the whole request
rolls back via `get_db()`, that rollback undoes everything since the transaction
began, including anything a released SAVEPOINT had already merged into it. That's
correct relational-database theory.

**First (misleading) check:** Querying the same session after rollback via
`db.get(...)` still showed the row. That's not proof of anything — `Session.get()`
serves from the identity map, and a rollback doesn't necessarily evict every cached
object before the next access re-triggers a load. This is exactly the trap: the ORM
told a story consistent with "the bug is real," but for the wrong reason.

**Real verification:** Bypassed the ORM entirely —
`db.execute(text("SELECT COUNT(*) FROM things")).scalar()` after the same
begin_nested → release → rollback sequence. Raw SQL, no identity map involved.
**Result: 1.** The row was actually still in the database. A parallel control test —
a *plain* `db.add(...); db.flush(); db.rollback()` with no SAVEPOINT involved —
correctly showed 0 rows via the same raw-SQL check. So the bug was specifically in
the SAVEPOINT-then-full-rollback sequence, isolated to this exact combination:
SQLite (pysqlite driver) + SQLAlchemy 2.0.52 + Python 3.14.7.

**Fix:** Both repositories were rewritten to skip `begin_nested()` entirely — a
plain `db.add(...)` + `db.flush()`, with an explicit `db.rollback()` in the
`except IntegrityError` branch. This is only safe because in both call sites, the
claim is always the *first* write in its request — there's nothing else in the
transaction yet for that rollback to discard. That constraint is documented in both
repositories' docstrings so it doesn't get violated by a future change that adds an
earlier write to either request path.

**Regression tests:**
[`test_reusing_a_key_for_a_failed_request_lets_a_corrected_retry_succeed`](../tests/test_idempotency.py)
and
[`test_retrying_a_failed_event_id_with_a_corrected_payload_succeeds`](../tests/test_processor_webhooks.py).

**Takeaway:** When a test's premise fails, check the assertion mechanism before
believing the failure. The ORM's identity map can make a rolled-back write look
like it persisted, and it can just as easily make a real write look absent. Raw SQL
is the ground truth when transaction semantics are actually in question.

---

## 4. `authorization.created` never validated its `merchant_reference`

**Symptom:** Found while writing the regression test for #3 above — constructing a
deliberately-invalid webhook payload (an unknown `research_record_id`) to trigger a
failure *didn't* fail. It succeeded, silently creating an `Authorization` row
pointing at a research record that didn't exist.

**Root cause:** SQLite doesn't enforce foreign-key constraints by default (no
`PRAGMA foreign_keys = ON`), and the handler never checked existence itself — it
just inserted whatever `research_record_id`/`user_id` the payload claimed. The
dangling reference would only have surfaced later, and confusingly, at settlement
time (`research_record_repository.get()` returning `None`), several steps removed
from the actual bad input.

**Fix:** [`app/services/processor_event_service.py`](../app/services/processor_event_service.py)'s
`_handle_authorization_created` now checks that both the research record and the
user exist before creating the authorization, failing fast with a clear message
instead of deferring to a confusing downstream error.

**Regression tests:**
`test_authorization_created_with_unknown_research_record_returns_400` and
`test_authorization_created_with_unknown_user_returns_400` in
[`tests/test_processor_webhooks.py`](../tests/test_processor_webhooks.py).

---

## Environment note (not a code bug, but cost real time)

Early in this project, `pip install -r requirements.txt` failed entirely —
`pydantic-core` doesn't ship a prebuilt wheel for Python 3.14 yet, which forced pip
to build it from source via Rust/maturin. That build then crashed with a
`UnicodeEncodeError` trying to print a build path containing non-ASCII characters
(the OneDrive-synced project path includes a Hebrew folder name). Not a bug in this
codebase, but worth recording: on a very new Python version, a source-build fallback
can fail for reasons that have nothing to do with the package itself. The fix was
unpinning and letting pip resolve to versions with actual 3.14 wheels.
