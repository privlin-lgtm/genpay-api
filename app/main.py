import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import accounts, archives, ledger, payments, records, users, webhooks
from app.config import settings
from app.database.db import Base, SessionLocal, engine
from app.database.seed_data import seed

# Import models so they register on Base.metadata before create_all runs.
from app.models import (  # noqa: F401
    authorization,
    historical_archive,
    idempotency_key,
    ledger_account,
    processed_webhook_event,
    research_record,
    settlement,
    transaction,
    user,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

_DEFAULT_SECRETS = {
    "secret_key": settings.secret_key,
    "webhook_signing_secret": settings.webhook_signing_secret,
    "internal_api_key": settings.internal_api_key,
}


def _check_secrets_are_not_defaults() -> None:
    """
    Fails startup rather than silently running with a secret that's public
    knowledge (it's literally the default in this repo's source). A webhook
    signature or API key check is worthless if the secret it's checked against
    is "change-me" for everyone who ever cloned this project.
    """
    if settings.env == "production":
        defaulted = [name for name, value in _DEFAULT_SECRETS.items() if value == "change-me"]
        if defaulted:
            raise RuntimeError(
                f"Refusing to start in production with default secret(s): {', '.join(defaulted)}. "
                "Set them via environment variables."
            )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _check_secrets_are_not_defaults()
    # create_all is a dev convenience so `uvicorn app.main:app` works with zero
    # setup — it's a no-op against a DB already at the current schema. Real
    # deployments should run `alembic upgrade head` as an explicit deploy step
    # instead of relying on this: create_all can't express a column rename, a
    # backfill, or a constraint change, only "table doesn't exist yet? create it."
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    yield


app = FastAPI(title="GenPay API", version="0.1.0", lifespan=lifespan)

app.include_router(users.router)
app.include_router(archives.router)
app.include_router(records.router)
app.include_router(accounts.router)
app.include_router(ledger.router)
app.include_router(payments.router)
app.include_router(webhooks.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
