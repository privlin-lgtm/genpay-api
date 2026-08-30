from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.historical_archive import HistoricalArchiveCreate, HistoricalArchiveRead
from app.services import archive_service

router = APIRouter(prefix="/archives", tags=["archives"])


@router.get("", response_model=list[HistoricalArchiveRead])
def list_archives(db: Session = Depends(get_db)) -> list[HistoricalArchiveRead]:
    return archive_service.list_archives(db)


@router.post("", response_model=HistoricalArchiveRead, status_code=201)
def create_archive(data: HistoricalArchiveCreate, db: Session = Depends(get_db)) -> HistoricalArchiveRead:
    return archive_service.create_archive(db, data)


@router.get("/{archive_id}", response_model=HistoricalArchiveRead)
def get_archive(archive_id: str, db: Session = Depends(get_db)) -> HistoricalArchiveRead:
    archive = archive_service.get_archive(db, archive_id)
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")
    return archive
