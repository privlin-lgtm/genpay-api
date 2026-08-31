import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api_client import ApiClient


def hash_key(raw_key: str) -> str:
    """
    SHA-256 of the raw key. Unlike a password, an API key is a high-entropy
    random-ish token the caller generates or is issued, not a low-entropy
    human-chosen secret — a fast hash is standard practice here (this is how
    Stripe/GitHub/etc. store API key hashes), unlike passwords, which need a
    slow, salted algorithm specifically to resist brute-forcing low-entropy input.
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def create(db: Session, name: str, raw_key: str) -> ApiClient:
    client = ApiClient(name=name, api_key_hash=hash_key(raw_key))
    db.add(client)
    db.flush()
    db.refresh(client)
    return client


def get_by_key(db: Session, raw_key: str) -> ApiClient | None:
    return db.scalar(select(ApiClient).where(ApiClient.api_key_hash == hash_key(raw_key)))


def get_by_name(db: Session, name: str) -> ApiClient | None:
    return db.scalar(select(ApiClient).where(ApiClient.name == name))
