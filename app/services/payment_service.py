from sqlalchemy.orm import Session

from app.models.authorization import AuthorizationStatus
from app.models.transaction import TransactionType
from app.repositories import (
    authorization_repository,
    ledger_account_repository,
    research_record_repository,
    settlement_repository,
    user_repository,
)
from app.schemas.purchase import PurchaseResult
from app.schemas.transaction import TransactionRead
from app.services.ledger_service import LedgerEntry, post_entries
from app.services.revenue_split import RevenueSplitConfig, split_amount


def purchase_record(
    db: Session, research_record_id: str, user_id: str, amount_cents: int | None = None
) -> PurchaseResult:
    """
    Synchronous demo path: authorize and immediately settle a researcher's purchase
    of a research record in one call. Used by POST /purchase and the legacy
    POST /webhooks/card-auth endpoint, which don't model a separate approval step.
    """
    record = research_record_repository.get(db, research_record_id)
    if record is None:
        raise ValueError(f"Research record not found: {research_record_id}")

    researcher = user_repository.get(db, user_id)
    if researcher is None:
        raise ValueError(f"User not found: {user_id}")

    total_cents = amount_cents if amount_cents is not None else record.price_cents
    authorization = authorization_repository.create(db, research_record_id, user_id, total_cents)
    return settle_authorization(db, authorization.id)


def settle_authorization(
    db: Session,
    authorization_id: str,
    settled_amount_cents: int | None = None,
    split_config: RevenueSplitConfig | None = None,
) -> PurchaseResult:
    """
    Settle an already-authorized hold: compute the revenue split and post a
    balanced ledger entry set. Used both by purchase_record() above and by the
    async processor-events webhook's settlement.completed handler.

    split_config overrides the configured default split (see app/config.py /
    app/services/revenue_split.py) for this call only — mainly for tests.
    """
    authorization = authorization_repository.get(db, authorization_id)
    if authorization is None:
        raise ValueError(f"Authorization not found: {authorization_id}")
    if authorization.status != AuthorizationStatus.authorized:
        raise ValueError(
            f"Cannot settle authorization {authorization_id} in status '{authorization.status.value}'"
        )
    if settlement_repository.get_by_authorization(db, authorization_id) is not None:
        raise ValueError(f"Authorization {authorization_id} has already been settled")

    record = research_record_repository.get(db, authorization.research_record_id)
    if record is None:
        raise ValueError(f"Research record not found: {authorization.research_record_id}")

    total_cents = settled_amount_cents if settled_amount_cents is not None else authorization.amount_cents

    split = split_amount(total_cents, split_config)
    archive_cents = split.archive_cents
    transcriptionist_cents = split.transcriptionist_cents
    platform_cents = split.platform_cents

    researcher_account = ledger_account_repository.get_by_owner_user(db, authorization.user_id)
    archive_account = ledger_account_repository.get_by_owner_archive(db, record.archive_id)
    platform_account = ledger_account_repository.get_platform_account(db)
    if not researcher_account or not archive_account or not platform_account:
        raise ValueError("Required ledger accounts are missing (researcher, archive, or platform)")

    transcriptionist_account = None
    if record.transcriptionist_user_id:
        transcriptionist_account = ledger_account_repository.get_by_owner_user(
            db, record.transcriptionist_user_id
        )

    # No assigned transcriptionist (or their ledger account is missing) — their
    # share rolls into the platform account rather than being lost.
    if transcriptionist_account is None:
        platform_cents += transcriptionist_cents
        transcriptionist_cents = 0

    settlement = settlement_repository.create(db, authorization.id, total_cents)

    entries = [LedgerEntry(researcher_account.id, TransactionType.debit, total_cents)]
    if archive_cents:
        entries.append(LedgerEntry(archive_account.id, TransactionType.credit, archive_cents))
    if transcriptionist_account and transcriptionist_cents:
        entries.append(LedgerEntry(transcriptionist_account.id, TransactionType.credit, transcriptionist_cents))
    if platform_cents:
        entries.append(LedgerEntry(platform_account.id, TransactionType.credit, platform_cents))

    transactions = post_entries(db, settlement.id, entries)

    return PurchaseResult(
        authorization_id=authorization.id,
        settlement_id=settlement.id,
        authorization_status=authorization.status,
        settlement_status=settlement.status,
        record_id=record.id,
        total_cents=total_cents,
        archive_cents=archive_cents,
        transcriptionist_cents=transcriptionist_cents,
        platform_cents=platform_cents,
        transactions=[TransactionRead.model_validate(t) for t in transactions],
    )
