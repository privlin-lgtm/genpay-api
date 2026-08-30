from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_api_key
from app.models.historical_archive import HistoricalArchive
from app.schemas.historical_archive import HistoricalArchiveCreate, HistoricalArchiveRead
from app.services import archive_service

router = APIRouter(prefix="/archives", tags=["archives"])


@router.get("", response_model=list[HistoricalArchiveRead])
def list_archives(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[HistoricalArchive]:
    return archive_service.list_archives(db, limit=limit, offset=offset)


@router.post(
    "", response_model=HistoricalArchiveRead, status_code=201, dependencies=[Depends(require_api_key)]
)
def create_archive(data: HistoricalArchiveCreate, db: Session = Depends(get_db)) -> HistoricalArchive:
    return archive_service.create_archive(db, data)


@router.get("/{archive_id}", response_model=HistoricalArchiveRead)
def get_archive(archive_id: str, db: Session = Depends(get_db)) -> HistoricalArchive:
    archive = archive_service.get_archive(db, archive_id)
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")
    return archive
