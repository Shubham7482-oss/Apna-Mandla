"""
app/routes/withdrawal.py

Withdrawal management — user-facing request + admin processing.
Prefix provided by api.py (/withdrawal); router has NO prefix.

Final paths:
  GET    /api/v1/withdrawal/my              — list my withdrawals
  GET    /api/v1/withdrawal/admin/pending   — admin: pending requests
  POST   /api/v1/withdrawal/admin/{id}/approve  — admin: approve + mark sent
  POST   /api/v1/withdrawal/admin/{id}/reject   — admin: reject + return funds
  GET    /api/v1/withdrawal/admin/verify-integrity — finance audit

Note: POST /wallet/withdraw (initiating a request) lives in wallets.py.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.rbac import require_finance_admin
from app.models.user import User
from app.models.wallet import Wallet
from app.models.withdrawal_request import WithdrawalRequest, WithdrawalStatus
from app.schemas.common import SuccessResponse
from app.services.ledger_service import WalletService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Withdrawal"])


# ─────────────────────────────────────────────────────────────────────────────
# GET /withdrawal/my
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/my")
def my_withdrawals(
    page:         int  = Query(1,  ge=1),
    page_size:    int  = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """List the current user's withdrawal requests, newest first."""
    q = (
        db.query(WithdrawalRequest)
        .filter(WithdrawalRequest.user_id == current_user.id)
        .order_by(WithdrawalRequest.created_at.desc())
    )
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return SuccessResponse(
        success=True,
        data={
            "page": page, "page_size": page_size, "total": total,
            "items": [
                {
                    "id":         r.id,
                    "amount":     float(r.amount),
                    "status":     r.status,
                    "created_at": r.created_at.isoformat(),
                    "batch_id":   r.settlement_batch_id,
                }
                for r in items
            ],
        },
        message="Withdrawal history fetched.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /withdrawal/admin/pending
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/admin/pending")
def pending_withdrawals(
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_finance_admin),
):
    """Return all PENDING withdrawal requests with totals by user type."""
    pending = (
        db.query(WithdrawalRequest, User)
        .join(User, User.id == WithdrawalRequest.user_id)
        .filter(WithdrawalRequest.status == WithdrawalStatus.PENDING)
        .order_by(WithdrawalRequest.created_at.asc())
        .all()
    )

    shops_total  = sum(r.amount for r, u in pending if u.user_type in ("SHOP", "SELLER"))
    riders_total = sum(r.amount for r, u in pending if u.user_type == "RIDER")

    return SuccessResponse(
        success=True,
        data={
            "shops_total":  float(shops_total),
            "riders_total": float(riders_total),
            "grand_total":  float(shops_total + riders_total),
            "count":        len(pending),
            "items": [
                {
                    "id":              r.id,
                    "user_id":         u.id,
                    "user_name":       u.name,
                    "user_type":       u.user_type,
                    "amount":          float(r.amount),
                    "bank_snapshot":   r.bank_details_snapshot,
                    "created_at":      r.created_at.isoformat(),
                }
                for r, u in pending
            ],
        },
        message="Pending withdrawals fetched.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /withdrawal/admin/{id}/approve
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/admin/{withdrawal_id}/approve")
def approve_withdrawal(
    withdrawal_id: int,
    db:            Session = Depends(get_db),
    admin:         User    = Depends(require_finance_admin),
):
    """
    Mark a withdrawal as COMPLETED (bank transfer has been sent).
    No ledger change — funds were already moved to escrow on initiation.
    """
    wr = (
        db.query(WithdrawalRequest)
        .filter(WithdrawalRequest.id == withdrawal_id)
        .with_for_update()
        .first()
    )
    if not wr:
        raise HTTPException(404, "Withdrawal request not found.")
    if wr.status != WithdrawalStatus.PENDING:
        raise HTTPException(400, f"Request is already {wr.status}, cannot approve.")

    wr.status          = WithdrawalStatus.COMPLETED
    wr.processed_by_id = admin.id
    wr.processed_at    = datetime.now(timezone.utc)
    db.commit()

    logger.info("withdrawal.approved id=%d by admin=%d", wr.id, admin.id)
    return SuccessResponse(success=True, message=f"Withdrawal #{wr.id} approved.")


# ─────────────────────────────────────────────────────────────────────────────
# POST /withdrawal/admin/{id}/reject
# ─────────────────────────────────────────────────────────────────────────────

class RejectBody(BaseModel):
    reason: Optional[str] = None


@router.post("/admin/{withdrawal_id}/reject")
def reject_withdrawal(
    withdrawal_id: int,
    body:          RejectBody = RejectBody(),
    db:            Session    = Depends(get_db),
    admin:         User       = Depends(require_finance_admin),
):
    """
    Reject a withdrawal and return the funds to the user's wallet.

    DR platform_wallet  amount  (REFUND)
    CR user_wallet      amount  (REFUND)
    """
    wr = (
        db.query(WithdrawalRequest)
        .filter(WithdrawalRequest.id == withdrawal_id)
        .with_for_update()
        .first()
    )
    if not wr:
        raise HTTPException(404, "Withdrawal request not found.")
    if wr.status != WithdrawalStatus.PENDING:
        raise HTTPException(400, f"Request is {wr.status}, cannot reject.")

    try:
        WalletService.reverse_withdrawal(
            db=db,
            user_id=wr.user_id,
            amount=wr.amount,
            withdrawal_id=wr.id,
        )
        wr.status          = WithdrawalStatus.REJECTED
        wr.admin_note      = body.reason
        wr.processed_by_id = admin.id
        wr.processed_at    = datetime.now(timezone.utc)
        db.commit()
        logger.info("withdrawal.rejected id=%d by admin=%d", wr.id, admin.id)
    except Exception:
        db.rollback()
        logger.exception("withdrawal.reject.error id=%d", withdrawal_id)
        raise HTTPException(500, "Rejection failed.")

    return SuccessResponse(success=True, message=f"Withdrawal #{wr.id} rejected and funds returned.")


# ─────────────────────────────────────────────────────────────────────────────
# GET /withdrawal/admin/verify-integrity
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/admin/verify-integrity")
def verify_integrity(
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_finance_admin),
):
    """Run a full mathematical audit of the ledger."""
    result = WalletService.verify_integrity(db)
    return SuccessResponse(
        success=True,
        data=result,
        message="Audit complete." if result["is_secure"] else "INTEGRITY ISSUES FOUND.",
    )
