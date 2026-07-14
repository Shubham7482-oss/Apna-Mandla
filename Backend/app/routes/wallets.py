"""
app/routes/wallets.py

Wallet API — prefix provided by api.py (/wallets), router has NO prefix.

Final paths:
  GET    /api/v1/wallets                — balance + stats
  GET    /api/v1/wallets/transactions   — paginated ledger history
  POST   /api/v1/wallets/add-money      — top up wallet (admin-verified)
  POST   /api/v1/wallets/pay            — pay for order from wallet balance
  POST   /api/v1/wallets/withdraw       — request a bank withdrawal
"""

import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.ledger_entry import LedgerEntry, TransactionPurpose
from app.models.order import Order, OrderStatus, PaymentMode
from app.models.shop import Shop
from app.models.shop_profile import ShopProfile
from app.models.user import User
from app.models.wallet import Wallet
from app.models.withdrawal_request import WithdrawalRequest, WithdrawalStatus
from app.schemas.common import SuccessResponse
from app.services.ledger_service import WalletService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Wallets"])


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class AddMoneyRequest(BaseModel):
    amount:          Decimal = Field(..., gt=0, le=100_000, description="Amount in INR")
    idempotency_key: Optional[str] = Field(None, max_length=100)
    description:     str = Field("Wallet top-up", max_length=200)

    @field_validator("amount", mode="before")
    @classmethod
    def round_amount(cls, v):
        return Decimal(str(v)).quantize(Decimal("0.01"))


class PayRequest(BaseModel):
    order_id:        int
    idempotency_key: Optional[str] = Field(None, max_length=100)


class WithdrawRequest(BaseModel):
    amount:          Decimal = Field(..., gt=0, le=500_000, description="Amount in INR")
    idempotency_key: Optional[str] = Field(None, max_length=100)

    @field_validator("amount", mode="before")
    @classmethod
    def round_amount(cls, v):
        return Decimal(str(v)).quantize(Decimal("0.01"))


# ─────────────────────────────────────────────────────────────────────────────
# GET /wallets   — wallet balance + summary
# ─────────────────────────────────────────────────────────────────────────────

@router.get("")
def get_wallet(
    current_user: User = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Return the current user's wallet balance and summary stats.
    Creates the wallet if it doesn't exist.
    """
    wallet = WalletService.get_or_create(db, current_user.id)
    db.commit()   # persist new wallet if created

    # Compute stats from ledger
    from sqlalchemy import case, func
    stats = (
        db.query(
            func.sum(
                case((LedgerEntry.entry_side == "CR", LedgerEntry.amount), else_=0)
            ).label("total_credited"),
            func.sum(
                case((LedgerEntry.entry_side == "DR", LedgerEntry.amount), else_=0)
            ).label("total_debited"),
            func.count(LedgerEntry.id).label("total_transactions"),
        )
        .filter(LedgerEntry.wallet_id == wallet.id)
        .first()
    )

    return SuccessResponse(
        success=True,
        data={
            "wallet_id":          wallet.id,
            "balance":            float(wallet.balance),
            "is_frozen":          wallet.is_frozen,
            "total_credited":     float(stats.total_credited or 0),
            "total_debited":      float(stats.total_debited or 0),
            "total_transactions": stats.total_transactions or 0,
        },
        message="Wallet fetched successfully.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /wallets/transactions  — paginated ledger history
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/transactions")
def get_transactions(
    page:             int   = Query(1,   ge=1),
    page_size:        int   = Query(20,  ge=1, le=100),
    transaction_type: Optional[str] = Query(None, description="Filter by purpose, e.g. ORDER_PAYMENT"),
    entry_side:       Optional[str] = Query(None, description="DR or CR"),
    current_user:     User = Depends(get_current_user),
    db:               Session = Depends(get_db),
):
    """
    Paginated transaction history for the current user's wallet.
    Returns entries newest-first.
    """
    wallet = WalletService.get_or_create(db, current_user.id)

    q = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.wallet_id == wallet.id)
    )

    if transaction_type:
        q = q.filter(LedgerEntry.transaction_type == transaction_type.upper())
    if entry_side:
        q = q.filter(LedgerEntry.entry_side == entry_side.upper())

    total   = q.count()
    entries = (
        q.order_by(LedgerEntry.sequence_number.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return SuccessResponse(
        success=True,
        data={
            "wallet_id": wallet.id,
            "balance":   float(wallet.balance),
            "page":      page,
            "page_size": page_size,
            "total":     total,
            "items": [
                {
                    "id":               e.id,
                    "sequence":         e.sequence_number,
                    "entry_side":       e.entry_side,
                    "transaction_type": e.transaction_type,
                    "amount":           float(e.amount),
                    "balance_after":    float(e.balance_after),
                    "description":      e.description,
                    "order_id":         e.order_id,
                    "withdrawal_id":    e.withdrawal_id,
                    "correlation_id":   e.correlation_id,
                    "created_at":       e.created_at.isoformat(),
                }
                for e in entries
            ],
        },
        message="Transactions fetched.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /wallets/add-money
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/add-money", status_code=status.HTTP_201_CREATED)
def add_money(
    body:         AddMoneyRequest,
    current_user: User = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Credit money to the current user's wallet.

    In production this endpoint should be called ONLY after successful
    payment gateway verification (Razorpay, PhonePe, etc.). The
    `idempotency_key` must be the payment gateway's transaction ID to
    prevent double-crediting if the gateway calls your webhook twice.

    For now it is open to authenticated users — add a gateway signature
    check before going live.
    """
    try:
        wallet = WalletService.topup(
            db=db,
            user_id=current_user.id,
            amount=body.amount,
            description=body.description,
            idempotency_key=body.idempotency_key,
        )
        db.commit()
        logger.info("wallet.topup user=%d amount=%s", current_user.id, body.amount)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception:
        db.rollback()
        logger.exception("wallet.topup.error user=%d", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to add money.")

    return SuccessResponse(
        success=True,
        data={"balance": float(wallet.balance)},
        message=f"₹{body.amount} added to wallet.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /wallets/pay
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/pay", status_code=status.HTTP_200_OK)
def pay_for_order(
    body:         PayRequest,
    current_user: User = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Pay for an order directly from wallet balance.

    The order must:
      - Belong to the current user (customer).
      - Be in PAYMENT_PENDING status.
      - Have payment_mode == PREPAID.
    """
    order = (
        db.query(Order)
        .filter(
            Order.id == body.order_id,
            Order.customer_id == current_user.id,
        )
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(404, "Order not found.")

    if order.status != OrderStatus.PAYMENT_PENDING:
        raise HTTPException(400, f"Order is in status '{order.status.value}', cannot pay.")

    if order.payment_mode != PaymentMode.PREPAID:
        raise HTTPException(400, "Order payment mode is not PREPAID.")

    # Resolve shop's user_id for ledger credit
    shop = db.query(Shop).filter(Shop.id == order.shop_id).first()
    if not shop:
        raise HTTPException(404, "Shop not found.")

    total = Decimal(str(order.total_amount))
    ik    = body.idempotency_key or f"wallet-pay-order-{order.id}"

    try:
        result = WalletService.process_order_payment(
            db=db,
            customer_id=current_user.id,
            shop_user_id=shop.user_id,
            total_amount=total,
            order_id=order.id,
            idempotency_key=ik,
        )
        order.status = OrderStatus.CREATED
        db.commit()
        logger.info(
            "wallet.pay order=%d customer=%d shop_user=%d total=%s",
            order.id, current_user.id, shop.user_id, total,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception:
        db.rollback()
        logger.exception("wallet.pay.error order=%d", body.order_id)
        raise HTTPException(500, "Payment failed. Please try again.")

    return SuccessResponse(
        success=True,
        data={
            "order_id":   order.id,
            "order_status": order.status.value,
            "total":      float(result["total"]),
            "commission": float(result["commission"]),
        },
        message="Payment successful.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /wallets/withdraw
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/withdraw", status_code=status.HTTP_201_CREATED)
def request_withdrawal(
    body:         WithdrawRequest,
    current_user: User = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Request a bank withdrawal of wallet balance.

    Only users with `user_type` SHOP or RIDER may withdraw.
    Bank details must be present on their profile.
    Amount is debited immediately; funds sit in escrow until admin approves.
    """
    if current_user.user_type not in ("SHOP", "SELLER", "RIDER"):
        raise HTTPException(403, "Only shops and riders may request withdrawals.")

    # ── Check bank details ────────────────────────────────────────────────────
    bank_snapshot: Optional[str] = None
    if current_user.user_type in ("SHOP", "SELLER"):
        profile = (
            db.query(ShopProfile)
            .filter(ShopProfile.user_id == current_user.id)
            .first()
        )
        bank_snapshot = profile.bank_details_json if profile else None
    else:
        from app.models.rider_profile import RiderProfile
        profile = (
            db.query(RiderProfile)
            .filter(RiderProfile.user_id == current_user.id)
            .first()
        )
        bank_snapshot = profile.bank_details_json if profile else None

    if not bank_snapshot:
        raise HTTPException(400, "Please update your bank details before withdrawing.")

    # ── Idempotency check ─────────────────────────────────────────────────────
    if body.idempotency_key:
        existing = (
            db.query(WithdrawalRequest)
            .filter(WithdrawalRequest.idempotency_key == body.idempotency_key)
            .first()
        )
        if existing:
            return SuccessResponse(
                success=True,
                data={"withdrawal_id": existing.id, "status": existing.status},
                message="Withdrawal already submitted.",
            )

    try:
        # 1. Create withdrawal request row
        wr = WithdrawalRequest(
            user_id=current_user.id,
            amount=body.amount,
            status=WithdrawalStatus.PENDING,
            idempotency_key=body.idempotency_key,
            bank_details_snapshot=bank_snapshot,
        )
        db.add(wr)
        db.flush()    # get wr.id before ledger entries reference it

        # 2. Debit wallet + credit escrow (double entry)
        WalletService.initiate_withdrawal(
            db=db,
            user_id=current_user.id,
            amount=body.amount,
            withdrawal_id=wr.id,
            idempotency_key=body.idempotency_key,
        )

        db.commit()
        logger.info("wallet.withdraw user=%d amount=%s wr=%d", current_user.id, body.amount, wr.id)

    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception:
        db.rollback()
        logger.exception("wallet.withdraw.error user=%d", current_user.id)
        raise HTTPException(500, "Withdrawal request failed.")

    return SuccessResponse(
        success=True,
        data={"withdrawal_id": wr.id, "status": wr.status},
        message=f"Withdrawal of ₹{body.amount} submitted. Admin will process it soon.",
    )
