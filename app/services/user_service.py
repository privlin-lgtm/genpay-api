from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import ledger_account_repository, user_repository
from app.schemas.user import UserCreate


def create_user(db: Session, data: UserCreate) -> User:
    """Create a user and provision their ledger account in one step."""
    user = user_repository.create(db, data)
    ledger_account_repository.create_for_user(db, user.id)
    return user


def get_user(db: Session, user_id: str) -> User | None:
    return user_repository.get(db, user_id)


def list_users(db: Session, limit: int = 50, offset: int = 0) -> list[User]:
    return user_repository.list_all(db, limit=limit, offset=offset)
