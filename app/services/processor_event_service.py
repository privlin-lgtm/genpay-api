import logging
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.authorization import AuthorizationStatus
from app.repositories import authorization_repository
from app.schemas.webhook import (
    AuthorizationApprovedData,
    AuthorizationCreatedData,
    AuthorizationDeclinedData,
    ProcessorEventEnvelope,
    SettlementCompletedData,
)
from app.services.payment_service import settle_authorization

logger = logging.getLogger("genpay.webhooks")


def handle_event(db: Session, envelope: ProcessorEventEnvelope) -> dict[str, Any]:
    handler = _HANDLERS.get(envelope.event_type)
    if handler is None:  # unreachable given the Literal type, kept as a defensive guard
        raise ValueError(f"Unsupported event_type: {envelope.event_type}")

    try:
        return handler(db, envelope.data)
    except ValidationError as exc:
        raise ValueError(f"Invalid payload for {envelope.event_type}: {exc}") from exc


def _handle_authorization_created(db: Session, data: dict) -> dict[str, Any]:
    payload = AuthorizationCreatedData.model_validate(data)

    if authorization_repository.get_by_external_reference(db, payload.authorization_id) is not None:
        raise ValueError(f"Authorization already exists: {payload.authorization_id}")

    authorization = authorization_repository.create_pending(
        db,
        research_record_id=payload.merchant_reference.research_record_id,
        user_id=payload.merchant_reference.user_id,
        amount_cents=payload.amount_cents,
        external_reference=payload.authorization_id,
    )
    logger.info(
        "authorization.created: hold requested",
        extra={
            "authorization_id": authorization.id,
            "processor_authorization_id": payload.authorization_id,
            "amount_cents": payload.amount_cents,
            "card_last4": payload.card_last4,
            "card_network": payload.card_network,
        },
    )
    return {"authorization_id": authorization.id, "status": authorization.status.value}


def _handle_authorization_approved(db: Session, data: dict) -> dict[str, Any]:
    payload = AuthorizationApprovedData.model_validate(data)
    authorization = _require_authorization(db, payload.authorization_id)

    if authorization.status != AuthorizationStatus.pending:
        raise ValueError(
            f"Cannot approve authorization {payload.authorization_id} in status "
            f"'{authorization.status.value}'"
        )

    authorization = authorization_repository.mark_approved(db, authorization)
    logger.info(
        "authorization.approved: hold created",
        extra={"authorization_id": authorization.id, "hold_expires_at": payload.hold_expires_at.isoformat()},
    )
    return {"authorization_id": authorization.id, "status": authorization.status.value}


def _handle_authorization_declined(db: Session, data: dict) -> dict[str, Any]:
    payload = AuthorizationDeclinedData.model_validate(data)
    authorization = _require_authorization(db, payload.authorization_id)

    if authorization.status != AuthorizationStatus.pending:
        raise ValueError(
            f"Cannot decline authorization {payload.authorization_id} in status "
            f"'{authorization.status.value}'"
        )

    authorization = authorization_repository.mark_declined(db, authorization, payload.decline_reason)
    logger.warning(
        "authorization.declined",
        extra={"authorization_id": authorization.id, "decline_reason": payload.decline_reason},
    )
    return {"authorization_id": authorization.id, "status": authorization.status.value}


def _handle_settlement_completed(db: Session, data: dict) -> dict[str, Any]:
    payload = SettlementCompletedData.model_validate(data)

    results = []
    for processor_authorization_id in payload.authorization_ids:
        authorization = _require_authorization(db, processor_authorization_id)
        result = settle_authorization(db, authorization.id)
        results.append(result.model_dump(mode="json"))
        logger.info(
            "settlement.completed: ledger posted",
            extra={
                "settlement_batch_id": payload.settlement_batch_id,
                "authorization_id": authorization.id,
                "settlement_id": result.settlement_id,
                "total_cents": result.total_cents,
            },
        )

    return {"settlement_batch_id": payload.settlement_batch_id, "settlements": results}


def _require_authorization(db: Session, processor_authorization_id: str):
    authorization = authorization_repository.get_by_external_reference(db, processor_authorization_id)
    if authorization is None:
        raise ValueError(f"Unknown authorization_id: {processor_authorization_id}")
    return authorization


_HANDLERS: dict[str, Callable[[Session, dict], dict[str, Any]]] = {
    "authorization.created": _handle_authorization_created,
    "authorization.approved": _handle_authorization_approved,
    "authorization.declined": _handle_authorization_declined,
    "settlement.completed": _handle_settlement_completed,
}
