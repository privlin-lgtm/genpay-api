from pydantic import BaseModel


class AccountDiscrepancy(BaseModel):
    ledger_account_id: str
    owner_type: str
    stored_balance_cents: int
    computed_balance_cents: int
    drift_cents: int


class ReconciliationReport(BaseModel):
    accounts_checked: int
    discrepancies: list[AccountDiscrepancy]

    @property
    def is_clean(self) -> bool:
        return len(self.discrepancies) == 0
