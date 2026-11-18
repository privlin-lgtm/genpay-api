"""
Output shapes for the tools, so each tool publishes an output schema.

Deliberately separate copies of the API's response fields rather than imports
of app.schemas: mcp_server only knows the API through HTTP. Money is integer
cents, exactly as the API returns it. Enum-valued fields are plain strings so a
new status on the API side doesn't break the server.
"""

from datetime import datetime

from pydantic import BaseModel


class Record(BaseModel):
    id: str
    archive_id: str
    record_reference: str
    title: str
    price_cents: int
    transcriptionist_user_id: str | None
    created_at: datetime


class Archive(BaseModel):
    id: str
    name: str
    description: str | None
    owner_user_id: str | None
    created_at: datetime


class Account(BaseModel):
    id: str
    owner_type: str
    owner_user_id: str | None
    owner_archive_id: str | None
    balance_cents: int
    currency: str
    status: str
    created_at: datetime


class LedgerTransaction(BaseModel):
    id: str
    ledger_account_id: str
    settlement_id: str
    type: str
    amount_cents: int
    currency: str
    status: str
    created_at: datetime


class Purchase(BaseModel):
    id: str
    research_record_id: str
    user_id: str
    amount_cents: int
    external_reference: str
    status: str
    created_by_client_id: str | None
    created_at: datetime


class AccountDiscrepancy(BaseModel):
    ledger_account_id: str
    owner_type: str
    stored_balance_cents: int
    computed_balance_cents: int
    drift_cents: int


class ReconciliationReport(BaseModel):
    accounts_checked: int
    discrepancies: list[AccountDiscrepancy]
    is_clean: bool
