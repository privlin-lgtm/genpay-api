from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate


def create(db: Session, data: UserCreate) -> User:
    user = User(name=data.name, email=data.email, role=data.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def list_all(db: Session) -> list[User]:
    return list(db.scalars(select(User)))
