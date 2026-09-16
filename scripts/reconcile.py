"""
Standalone reconciliation check, meant to run on a schedule (cron, a scheduled
CI workflow, etc.) against the real DATABASE_URL — not through the API, so it
doesn't need an API key and keeps working even if the app itself is down.

Exits 0 with no output if every ledger account's stored balance matches the sum
of its posted transactions; exits 1 and prints each discrepancy otherwise, so a
scheduler can alert on a non-zero exit code.

Usage:
    DATABASE_URL=postgresql+psycopg://... python scripts/reconcile.py
"""

import sys

from app.database.db import SessionLocal

# Import every model so they all register on Base.metadata before any query
# runs — reconcile_all queries LedgerAccount/Transaction, and LedgerAccount's
# relationships reference User/HistoricalArchive by name, so mapper
# configuration fails at query time unless those are registered too.
from app.models import (  # noqa: F401
    api_client,
    authorization,
    historical_archive,
    idempotency_key,
    ledger_account,
    processed_webhook_event,
    research_record,
    settlement,
    transaction,
    user,
)
from app.services.reconciliation_service import reconcile_all


def main() -> int:
    db = SessionLocal()
    try:
        report = reconcile_all(db)
    finally:
        db.close()

    if report.is_clean:
        print(f"OK: {report.accounts_checked} account(s) checked, no discrepancies.")
        return 0

    print(
        f"RECONCILIATION FAILED: {len(report.discrepancies)} of "
        f"{report.accounts_checked} account(s) drifted from their transaction history:"
    )
    for d in report.discrepancies:
        print(
            f"  account={d.ledger_account_id} ({d.owner_type}): "
            f"stored={d.stored_balance_cents} computed={d.computed_balance_cents} "
            f"drift={d.drift_cents}"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
