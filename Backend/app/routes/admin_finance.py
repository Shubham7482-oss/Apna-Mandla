"""
app/routes/admin_finance.py

Admin finance dashboard — platform-level financial overview.
Router has NO self-prefix; api.py provides /admin/finance.

Final paths:
  GET  /api/v1/admin/finance/summary          — live P&L snapshot
  GET  /api/v1/admin/finance/commission       — active commission config
  POST /api/v1/admin/finance/commission       — update commission (rotation-safe)
  GET  /api/v1/admin/finance/withdrawals/pending  — pending withdrawal list + totals
  POST /api/v1/admin/finance/withdrawals/{id}/approve
  POST /api/v1/admin/finance/withdrawals/{id}/reject
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rbac import require_admin, require_finance_admin
from app.models.commission import CommissionConfig
from app.models.ledger_entry import LedgerEntry
from app.models.user import User
from app.models.wallet import Wallet
from app.models.withdrawal_request import WithdrawalRequest, WithdrawalStatus
from app.schemas.common import SuccessResponse
from app.services.ledger_service import WalletService, PLATFORM_USER_ID

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin Finance"])


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/finance/summary
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/summary")
def financial_summary(
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_finance_admin),
):
    """
    Live platform financial snapshot.
    All figures derived from ledger entries — never stale cached values.
    """
    # Platform wallet balance (user_id == PLATFORM_USER_ID)
    platform_wallet = WalletService.get_or_create(db, PLATFORM_USER_ID)

    # Total CR / DR across all ledger entries
    totals = (
        db.query(
            func.coalesce(
                func.sum(case((LedgerEntry.entry_side == "CR", LedgerEntry.amount), else_=0)), 0
            ).label("total_cr"),
            func.coalesce(
                func.sum(case((LedgerEntry.entry_side == "DR", LedgerEntry.amount), else_=0)), 0
            ).label("total_dr"),
            func.count(LedgerEntry.id).label("total_entries"),
        )
        .first()
    )

    # Commission earned (type == COMMISSION, side == CR on platform wallet)
    commission_earned = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount), 0))
        .filter(
            LedgerEntry.wallet_id == platform_wallet.id,
            LedgerEntry.transaction_type == "COMMISSION",
            LedgerEntry.entry_side == "CR",
        )
        .scalar()
    ) or Decimal("0")

    # Pending withdrawals
    pending_wd = (
        db.query(func.coalesce(func.sum(WithdrawalRequest.amount), 0))
        .filter(WithdrawalRequest.status == WithdrawalStatus.PENDING)
        .scalar()
    ) or Decimal("0")

    # Negative wallet check
    negative_count = (
        db.query(func.count(Wallet.id))
        .filter(Wallet.balance < 0)
        .scalar()
    ) or 0

    return SuccessResponse(
        success=True,
        data={
            "platform_balance":    float(platform_wallet.balance),
            "total_cr_ever":       float(totals.total_cr),
            "total_dr_ever":       float(totals.total_dr),
            "ledger_entries":      totals.total_entries,
            "commission_earned":   float(commission_earned),
            "pending_withdrawals": float(pending_wd),
            "negative_wallets":    negative_count,
            "is_balanced":         abs(Decimal(str(totals.total_cr)) - Decimal(str(totals.total_dr))) < Decimal("0.01"),
        },
        message="Financial summary fetched.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/finance/commission
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/commission")
def get_commission(
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_admin),
):
    cfg = (
        db.query(CommissionConfig)
        .filter(CommissionConfig.is_active == True)  # noqa: E712
        .order_by(CommissionConfig.created_at.desc())
        .first()
    )
    if not cfg:
        raise HTTPException(404, "No active commission configuration found.")
    return SuccessResponse(
        success=True,
        data={"id": cfg.id, "percent": str(cfg.percent), "created_at": cfg.created_at.isoformat()},
        message="Active commission fetched.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/finance/commission
# ─────────────────────────────────────────────────────────────────────────────

class CommissionBody(BaseModel):
    percent: Decimal


@router.post("/commission", status_code=status.HTTP_201_CREATED)
def set_commission(
    body:  CommissionBody,
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_admin),
):
    """Rotation-safe commission update: deactivates old, inserts new."""
    if body.percent < 0 or body.percent > 100:
        raise HTTPException(400, "Commission must be between 0% and 100%.")
    try:
        current = (
            db.query(CommissionConfig)
            .filter(CommissionConfig.is_active == True)  # noqa: E712
            .with_for_update()
            .first()
        )
        if current:
            current.is_active = False
        new_cfg = CommissionConfig(percent=body.percent, is_active=True)
        db.add(new_cfg)
        db.commit()
        db.refresh(new_cfg)
        logger.info("admin.commission.updated percent=%s by admin=%d", body.percent, admin.id)
    except Exception:
        db.rollback()
        raise HTTPException(500, "Commission update failed.")
    return SuccessResponse(
        success=True,
        data={"id": new_cfg.id, "percent": str(new_cfg.percent)},
        message=f"Commission updated to {body.percent}%.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/finance/withdrawals/pending
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/withdrawals/pending")
def pending_withdrawals(
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_finance_admin),
):
    rows = (
        db.query(WithdrawalRequest, User)
        .join(User, User.id == WithdrawalRequest.user_id)
        .filter(WithdrawalRequest.status == WithdrawalStatus.PENDING)
        .order_by(WithdrawalRequest.created_at.asc())
        .all()
    )
    shops_total  = sum(r.amount for r, u in rows if u.user_type in ("SHOP", "SELLER"))
    riders_total = sum(r.amount for r, u in rows if u.user_type == "RIDER")
    return SuccessResponse(
        success=True,
        data={
            "shops_total":  float(shops_total),
            "riders_total": float(riders_total),
            "grand_total":  float(shops_total + riders_total),
            "count":        len(rows),
            "items": [
                {
                    "id":           r.id,
                    "user_id":      u.id,
                    "user_name":    u.name,
                    "user_type":    u.user_type,
                    "amount":       float(r.amount),
                    "bank_snapshot":r.bank_details_snapshot,
                    "created_at":   r.created_at.isoformat(),
                }
                for r, u in rows
            ],
        },
        message="Pending withdrawals fetched.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/finance/withdrawals/{id}/approve
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/withdrawals/{withdrawal_id}/approve")
def approve_withdrawal(
    withdrawal_id: int,
    db:            Session = Depends(get_db),
    admin:         User    = Depends(require_finance_admin),
):
    wr = (
        db.query(WithdrawalRequest)
        .filter(WithdrawalRequest.id == withdrawal_id)
        .with_for_update()
        .first()
    )
    if not wr:
        raise HTTPException(404, "Withdrawal not found.")
    if wr.status != WithdrawalStatus.PENDING:
        raise HTTPException(400, f"Withdrawal is {wr.status}, cannot approve.")
    wr.status          = WithdrawalStatus.COMPLETED
    wr.processed_by_id = admin.id
    wr.processed_at    = datetime.now(timezone.utc)
    db.commit()
    logger.info("withdrawal.approved id=%d by admin=%d", wr.id, admin.id)
    return SuccessResponse(success=True, message=f"Withdrawal #{wr.id} approved.")


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/finance/withdrawals/{id}/reject
# ─────────────────────────────────────────────────────────────────────────────

class RejectBody(BaseModel):
    reason: Optional[str] = None


@router.post("/withdrawals/{withdrawal_id}/reject")
def reject_withdrawal(
    withdrawal_id: int,
    body:          RejectBody = RejectBody(),
    db:            Session    = Depends(get_db),
    admin:         User       = Depends(require_finance_admin),
):
    wr = (
        db.query(WithdrawalRequest)
        .filter(WithdrawalRequest.id == withdrawal_id)
        .with_for_update()
        .first()
    )
    if not wr:
        raise HTTPException(404, "Withdrawal not found.")
    if wr.status != WithdrawalStatus.PENDING:
        raise HTTPException(400, f"Withdrawal is {wr.status}, cannot reject.")
    try:
        WalletService.reverse_withdrawal(db=db, user_id=wr.user_id, amount=wr.amount, withdrawal_id=wr.id)
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
    return SuccessResponse(success=True, message=f"Withdrawal #{wr.id} rejected — funds returned.")
