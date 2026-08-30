import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import accounts, archives, ledger, payments, records, users, webhooks
from app.database.db import Base, SessionLocal, engine
from app.database.seed_data import seed

# Import models so they register on Base.metadata before create_all runs.
from app.models import (  # noqa: F401
    authorization,
    historical_archive,
    ledger_account,
    processed_webhook_event,
    research_record,
    settlement,
    transaction,
    user,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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
