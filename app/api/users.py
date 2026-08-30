from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_api_key
from app.models.user import User
from app.schemas.user import UserCreate, UserRead
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[UserRead])
def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[User]:
    return user_service.list_users(db, limit=limit, offset=offset)


@router.post("", response_model=UserRead, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db)) -> User:
    return user_service.create_user(db, data)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: str, db: Session = Depends(get_db)) -> User:
    user = user_service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
