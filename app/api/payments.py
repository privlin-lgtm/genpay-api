from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories import authorization_repository
from app.schemas.purchase import PurchaseDetail, PurchaseRequest, PurchaseResult
from app.services.payment_service import purchase_record

router = APIRouter(tags=["payments"])


@router.post("/purchase", response_model=PurchaseResult)
def purchase(data: PurchaseRequest, db: Session = Depends(get_db)) -> PurchaseResult:
    try:
        return purchase_record(db, research_record_id=data.research_record_id, user_id=data.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/purchases/{authorization_id}", response_model=PurchaseDetail)
def get_purchase(authorization_id: str, db: Session = Depends(get_db)) -> PurchaseDetail:
    authorization = authorization_repository.get(db, authorization_id)
    if not authorization:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return authorization
