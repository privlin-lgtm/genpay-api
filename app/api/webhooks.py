import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.repositories import processed_webhook_event_repository
from app.schemas.purchase import PurchaseResult
from app.schemas.webhook import CardAuthorizationEvent, ProcessorEventEnvelope
from app.security.webhook_signature import verify_webhook_signature
from app.services.processor_event_service import handle_event
from app.services.settlement_service import handle_card_authorization

logger = logging.getLogger("genpay.webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

require_valid_signature = verify_webhook_signature(settings.webhook_signing_secret)


@router.post("/card-auth", response_model=PurchaseResult)
def card_authorization(event: CardAuthorizationEvent, db: Session = Depends(get_db)) -> PurchaseResult:
    """Legacy synchronous demo path — authorizes and settles a purchase in one call."""
    try:
        return handle_card_authorization(db, event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/processor-events")
def processor_events(
    db: Session = Depends(get_db),
    raw_body: bytes = Depends(require_valid_signature),
) -> dict:
    """
    Receives the simulated issuer processor's event stream:
    authorization.created, authorization.approved, authorization.declined,
    settlement.completed. Requires a valid X-GenPay-Signature header (see
    app/security/webhook_signature.py) and is idempotent per event_id.
    """
    try:
        envelope = ProcessorEventEnvelope.model_validate_json(raw_body)
    except ValidationError as exc:
        logger.warning("webhook.malformed_payload", extra={"error": str(exc)})
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "malformed_payload", "message": "Could not parse webhook payload"}},
        ) from exc

    logger.info(
        "webhook.received", extra={"event_id": envelope.event_id, "event_type": envelope.event_type}
    )

    if processed_webhook_event_repository.has_processed(db, envelope.event_id):
        logger.info("webhook.duplicate_ignored", extra={"event_id": envelope.event_id})
        return {"status": "ignored", "reason": "already_processed", "event_id": envelope.event_id}

    try:
        result = handle_event(db, envelope)
    except ValueError as exc:
        logger.error(
            "webhook.processing_failed",
            extra={"event_id": envelope.event_id, "event_type": envelope.event_type, "error": str(exc)},
        )
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "event_processing_failed", "message": str(exc)}},
        ) from exc

    if not processed_webhook_event_repository.mark_processed(db, envelope.event_id, envelope.event_type):
        # Lost the race to a concurrent delivery of the same event_id: the
        # has_processed check above and this insert aren't one atomic operation,
        # so both requests could have run the handler. Each handler has its own
        # domain-level guard (existence/status checks in processor_event_service),
        # which prevents duplicate ledger postings in the common case, but this
        # isn't a hard guarantee without row-level locking on the authorization.
        logger.warning("webhook.duplicate_after_processing", extra={"event_id": envelope.event_id})
        return {"status": "ignored", "reason": "already_processed", "event_id": envelope.event_id}

    logger.info(
        "webhook.processed", extra={"event_id": envelope.event_id, "event_type": envelope.event_type}
    )
    return {"status": "processed", "event_id": envelope.event_id, "result": result}
