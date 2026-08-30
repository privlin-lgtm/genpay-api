from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.research_record import ResearchRecordCreate, ResearchRecordRead
from app.services import record_service

router = APIRouter(prefix="/records", tags=["records"])


@router.get("", response_model=list[ResearchRecordRead])
def list_records(db: Session = Depends(get_db)) -> list[ResearchRecordRead]:
    return record_service.list_records(db)


@router.post("", response_model=ResearchRecordRead, status_code=201)
def create_record(data: ResearchRecordCreate, db: Session = Depends(get_db)) -> ResearchRecordRead:
    return record_service.create_record(db, data)


@router.get("/{record_id}", response_model=ResearchRecordRead)
def get_record(record_id: str, db: Session = Depends(get_db)) -> ResearchRecordRead:
    record = record_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record
