"""
app/routes/admin_ledger.py

Admin ledger and reconciliation endpoints.
Router has NO self-prefix — api.py provides /admin/ledger.

Final paths:
  GET  /api/v1/admin/ledger/verify              — quick hash-chain check
  GET  /api/v1/admin/reconciliation             — latest reconciliation report
  POST /api/v1/admin/reconciliation/run         — trigger reconciliation manually
  GET  /api/v1/admin/fraud-flags                — list unresolved fraud flags
  POST /api/v1/admin/fraud-flags/{id}/resolve   — resolve a fraud flag
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.rbac import require_admin, require_finance_admin
from app.models.fraud_flag import FraudFlag
from app.models.reconciliation_report import ReconciliationReport
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.services.reconciliation_service import ReconciliationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin Ledger"])


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/ledger/verify
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/verify")
def verify_ledger(
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_admin),
):
    """Quick hash-chain integrity check (does NOT persist a report)."""
    from app.services.ledger_service import WalletService
    result = WalletService.verify_integrity(db)
    if not result["is_secure"]:
        raise HTTPException(500, detail=result)
    return SuccessResponse(success=True, data=result, message="Ledger chain intact.")


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/reconciliation
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/reconciliation")
def get_latest_reconciliation(
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_finance_admin),
):
    """Return the most recent reconciliation report."""
    report = ReconciliationService.latest_report(db)
    if not report:
        raise HTTPException(404, "No reconciliation reports found. Run one first.")

    issues = [] if not report.issues_json else __import__("json").loads(report.issues_json)

    return SuccessResponse(
        success=True,
        data={
            "id":                   report.id,
            "trigger_type":         report.trigger_type,
            "is_clean":             report.is_clean,
            "total_entries":        report.total_entries,
            "wallets_checked":      report.wallets_checked,
            "correlations_checked": report.correlations_checked,
            "issues_found":         report.issues_found,
            "total_cr_sum":         float(report.total_cr_sum),
            "total_dr_sum":         float(report.total_dr_sum),
            "duration_ms":          report.duration_ms,
            "issues":               issues,
            "created_at":           report.created_at.isoformat(),
        },
        message="Latest reconciliation report fetched.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/reconciliation/run
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/reconciliation/run")
def run_reconciliation(
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_finance_admin),
):
    """
    Trigger a full reconciliation run immediately.
    Persists a ReconciliationReport row.
    """
    try:
        report = ReconciliationService.run(
            db=db,
            triggered_by_id=admin.id,
            trigger_type="MANUAL",
        )
        db.commit()
        logger.info("admin.reconciliation.run by admin=%d issues=%d", admin.id, report.issues_found)
    except Exception:
        db.rollback()
        logger.exception("admin.reconciliation.run.error")
        raise HTTPException(500, "Reconciliation failed.")

    issues = [] if not report.issues_json else __import__("json").loads(report.issues_json)

    return SuccessResponse(
        success=True,
        data={
            "id":           report.id,
            "is_clean":     report.is_clean,
            "issues_found": report.issues_found,
            "total_entries":report.total_entries,
            "duration_ms":  report.duration_ms,
            "issues":       issues[:20],   # cap response size
        },
        message="Reconciliation complete." if report.is_clean else f"⚠ {report.issues_found} issue(s) found.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/fraud-flags
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/fraud-flags")
def list_fraud_flags(
    unresolved_only: bool = Query(True),
    severity:        Optional[str] = Query(None),
    page:            int  = Query(1, ge=1),
    page_size:       int  = Query(20, ge=1, le=100),
    db:              Session = Depends(get_db),
    admin:           User    = Depends(require_admin),
):
    """List fraud flags for review."""
    q = db.query(FraudFlag)
    if unresolved_only:
        q = q.filter(FraudFlag.is_resolved == False)  # noqa: E712
    if severity:
        q = q.filter(FraudFlag.severity == severity.upper())
    total = q.count()
    flags = (
        q.order_by(FraudFlag.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return SuccessResponse(
        success=True,
        data={
            "page": page, "page_size": page_size, "total": total,
            "items": [
                {
                    "id":             f.id,
                    "user_id":        f.user_id,
                    "flag_type":      f.flag_type,
                    "severity":       f.severity,
                    "amount":         float(f.amount) if f.amount else None,
                    "description":    f.description,
                    "is_resolved":    f.is_resolved,
                    "ip_address":     f.ip_address,
                    "created_at":     f.created_at.isoformat(),
                }
                for f in flags
            ],
        },
        message=f"{total} fraud flag(s) found.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/fraud-flags/{id}/resolve
# ─────────────────────────────────────────────────────────────────────────────

class ResolveBody(BaseModel):
    note: Optional[str] = None


@router.post("/fraud-flags/{flag_id}/resolve")
def resolve_fraud_flag(
    flag_id: int,
    body:    ResolveBody = ResolveBody(),
    db:      Session     = Depends(get_db),
    admin:   User        = Depends(require_admin),
):
    flag = db.query(FraudFlag).filter(FraudFlag.id == flag_id).first()
    if not flag:
        raise HTTPException(404, "Fraud flag not found.")
    if flag.is_resolved:
        return SuccessResponse(success=True, message="Already resolved.")

    flag.is_resolved     = True
    flag.resolved_by_id  = admin.id
    flag.resolved_at     = datetime.now(timezone.utc)
    flag.resolution_note = body.note
    db.commit()

    logger.info("fraud.flag.resolved id=%d by admin=%d", flag_id, admin.id)
    return SuccessResponse(success=True, message=f"Fraud flag #{flag_id} resolved.")
