from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_api_key
from app.models.research_record import ResearchRecord
from app.schemas.research_record import ResearchRecordCreate, ResearchRecordRead
from app.services import record_service

router = APIRouter(prefix="/records", tags=["records"])


@router.get("", response_model=list[ResearchRecordRead])
def list_records(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[ResearchRecord]:
    return record_service.list_records(db, limit=limit, offset=offset)


@router.post(
    "", response_model=ResearchRecordRead, status_code=201, dependencies=[Depends(require_api_key)]
)
def create_record(data: ResearchRecordCreate, db: Session = Depends(get_db)) -> ResearchRecord:
    return record_service.create_record(db, data)


@router.get("/{record_id}", response_model=ResearchRecordRead)
def get_record(record_id: str, db: Session = Depends(get_db)) -> ResearchRecord:
    record = record_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record
