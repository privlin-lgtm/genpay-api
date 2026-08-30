from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_api_key
from app.repositories import authorization_repository, idempotency_key_repository
from app.schemas.purchase import PurchaseDetail, PurchaseRequest, PurchaseResult
from app.services.payment_service import purchase_record

router = APIRouter(tags=["payments"], dependencies=[Depends(require_api_key)])


@router.post("/purchase", response_model=PurchaseResult)
def purchase(
    data: PurchaseRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> PurchaseResult:
    """
    Idempotency-Key is required: without it, a client retry after a timed-out
    request (the client can never be sure whether the first attempt landed)
    creates a second real purchase — a second Authorization, Settlement, and set
    of ledger postings for what the client believes is one purchase.
    """
    if cached := idempotency_key_repository.get(db, idempotency_key):
        return PurchaseResult.model_validate_json(cached)

    if not idempotency_key_repository.try_claim(db, idempotency_key):
        raise HTTPException(
            status_code=409,
            detail="A request with this Idempotency-Key is already in progress or has completed",
        )

    try:
        result = purchase_record(db, research_record_id=data.research_record_id, user_id=data.user_id)
    except ValueError as exc:
        # get_db() rolls back this whole request on the exception, including the
        # claim above — the key isn't burned, so a corrected retry can reuse it.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    idempotency_key_repository.store_result(db, idempotency_key, result.model_dump_json())
    return result


@router.get("/purchases/{authorization_id}", response_model=PurchaseDetail)
def get_purchase(authorization_id: str, db: Session = Depends(get_db)) -> PurchaseDetail:
    authorization = authorization_repository.get(db, authorization_id)
    if not authorization:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return authorization
