import logging

from fastapi import APIRouter, Depends, HTTPException, Request
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
async def card_authorization(request: Request, db: Session = Depends(get_db)) -> PurchaseResult:
    """
    Legacy synchronous demo path — authorizes and settles a purchase in one call.

    Parses the request body via model_validate_json() rather than letting FastAPI
    inject an already-json.loads()'d dict: `amount` is a Decimal, and validating
    straight from the raw JSON text lets pydantic-core read "5.99" as an exact
    decimal instead of round-tripping it through a Python float first.
    """
    raw_body = await request.body()
    try:
        event = CardAuthorizationEvent.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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

    if not processed_webhook_event_repository.try_claim(db, envelope.event_id, envelope.event_type):
        logger.info("webhook.duplicate_ignored", extra={"event_id": envelope.event_id})
        return {"status": "ignored", "reason": "already_processed", "event_id": envelope.event_id}

    try:
        result = handle_event(db, envelope)
    except ValueError as exc:
        logger.error(
            "webhook.processing_failed",
            extra={"event_id": envelope.event_id, "event_type": envelope.event_type, "error": str(exc)},
        )
        # get_db() rolls back the whole request on this exception, including the
        # claim row above — the event_id is not burned, a corrected retry can
        # still succeed.
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "event_processing_failed", "message": str(exc)}},
        ) from exc

    logger.info(
        "webhook.processed", extra={"event_id": envelope.event_id, "event_type": envelope.event_type}
    )
    return {"status": "processed", "event_id": envelope.event_id, "result": result}
