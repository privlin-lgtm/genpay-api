from sqlalchemy.orm import Session

from app.models.api_client import ApiClient
from app.repositories import api_client_repository


def authenticate(db: Session, raw_key: str) -> ApiClient | None:
    """Return the active ApiClient whose key hash matches raw_key, or None."""
    client = api_client_repository.get_by_key(db, raw_key)
    if client is None or not client.is_active:
        return None
    return client
