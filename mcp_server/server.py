from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_server.client import GenPayClient
from mcp_server.models import (
    Account,
    Archive,
    LedgerTransaction,
    Purchase,
    ReconciliationReport,
    Record,
)

# Every tool is a GET: no side effects, safe to repeat, and it only talks to GenPay.
READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)

Limit = Annotated[int, Field(ge=1, le=200, description="Page size, 1-200.")]
Offset = Annotated[int, Field(ge=0, description="Items to skip, for paging.")]
# Ids are UUIDs. The pattern also keeps an id from changing the path it's put
# into ("../accounts", "x?y=1"), so a tool can only ever reach its own route.
Id = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$")]

INSTRUCTIONS = (
    "Read-only access to GenPay, a genealogy-records marketplace with a double-entry ledger. "
    "All amounts are integer cents."
)


def build_server(genpay: GenPayClient) -> MCPServer:
    server = MCPServer("genpay", instructions=INSTRUCTIONS)

    @server.tool(annotations=READ_ONLY, description="List purchasable census records with their prices.")
    def list_records(limit: Limit = 50, offset: Offset = 0) -> list[Record]:
        rows = genpay.get("/records", {"limit": limit, "offset": offset})
        return [Record.model_validate(r) for r in rows]

    @server.tool(annotations=READ_ONLY, description="Get one research record by id.")
    def get_record(record_id: Id) -> Record:
        return Record.model_validate(genpay.get(f"/records/{record_id}"))

    @server.tool(annotations=READ_ONLY, description="List the historical archives that publish records.")
    def list_archives(limit: Limit = 50, offset: Offset = 0) -> list[Archive]:
        rows = genpay.get("/archives", {"limit": limit, "offset": offset})
        return [Archive.model_validate(r) for r in rows]

    @server.tool(
        annotations=READ_ONLY,
        description="List ledger accounts (platform, archives, users) with balances in integer cents.",
    )
    def list_accounts(limit: Limit = 50, offset: Offset = 0) -> list[Account]:
        rows = genpay.get("/accounts", {"limit": limit, "offset": offset})
        return [Account.model_validate(r) for r in rows]

    @server.tool(annotations=READ_ONLY, description="Get one ledger account and its balance by id.")
    def get_account(account_id: Id) -> Account:
        return Account.model_validate(genpay.get(f"/accounts/{account_id}"))

    @server.tool(
        annotations=READ_ONLY,
        description="List ledger transactions (debits and credits), optionally for one account.",
    )
    def list_ledger_transactions(
        account_id: Id | None = None, limit: Limit = 50, offset: Offset = 0
    ) -> list[LedgerTransaction]:
        rows = genpay.get("/ledger", {"account_id": account_id, "limit": limit, "offset": offset})
        return [LedgerTransaction.model_validate(r) for r in rows]

    @server.tool(annotations=READ_ONLY, description="Get one purchase (card authorization) by its id.")
    def get_purchase(authorization_id: Id) -> Purchase:
        return Purchase.model_validate(genpay.get(f"/purchases/{authorization_id}"))

    @server.tool(
        annotations=READ_ONLY,
        description=(
            "Check that every ledger account's stored balance equals the sum of its transactions. "
            "Read-only: reports discrepancies, changes nothing."
        ),
    )
    def run_reconciliation() -> ReconciliationReport:
        report = genpay.get("/reconciliation")
        return ReconciliationReport.model_validate({**report, "is_clean": not report.get("discrepancies")})

    return server
