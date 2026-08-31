from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_api_key
from app.schemas.reconciliation import ReconciliationReport
from app.services.reconciliation_service import reconcile_all

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=ReconciliationReport)
def get_reconciliation_report(db: Session = Depends(get_db)) -> ReconciliationReport:
    """
    Confirms every ledger account's stored balance still matches the sum of its
    posted transactions. Intended for both manual/on-demand checks and a
    scheduled job (see scripts/reconcile.py and
    .github/workflows/reconciliation.yml) — a real deployment would point that
    job at the production DATABASE_URL and alert on any non-empty
    `discrepancies` list.
    """
    return reconcile_all(db)
