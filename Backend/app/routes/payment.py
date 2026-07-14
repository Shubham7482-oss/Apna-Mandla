"""
app/routes/payment.py

Payment gateway integration routes.
Prefix provided by api.py (/payment); router has NO prefix.

Final paths:
  POST /api/v1/payment/success     — gateway callback: mark payment done + settle ledger
  POST /api/v1/payment/failed      — gateway callback: mark payment failed
  POST /api/v1/payment/{id}/refund — admin: refund a completed payment
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.rbac import require_roles, require_admin
from app.models.order import Order, OrderStatus
from app.models.payment import Payment
from app.models.shop import Shop
from app.models.user import User
from app.services.ledger_service import WalletService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Payment"])


# ─────────────────────────────────────────────────────────────────────────────
# POST /payment/success
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/success")
def payment_success(
    payment_id:     int,
    transaction_id: str,
    current_user:   User    = Depends(require_roles(["customer"])),
    db:             Session = Depends(get_db),
):
    """
    Called by the payment gateway (or client after gateway confirmation).
    Marks the payment SUCCESS, settles the order, and posts ledger entries.
    Idempotent: re-calling with the same transaction_id is a no-op.
    """
    payment = (
        db.query(Payment)
        .filter(
            Payment.id == payment_id,
            Payment.user_id == current_user.id,
        )
        .with_for_update()
        .first()
    )
    if not payment:
        raise HTTPException(404, "Payment not found.")

    # Idempotency — already processed
    if payment.status == "SUCCESS":
        return {"message": "Payment already processed.", "payment_id": payment.id}

    if payment.status != "INITIATED":
        raise HTTPException(400, f"Invalid payment state: {payment.status}")

    # Prevent duplicate transaction_id across all payments
    dup = db.query(Payment).filter(Payment.transaction_id == transaction_id).first()
    if dup and dup.id != payment.id:
        raise HTTPException(400, "Transaction ID already used by another payment.")

    order = (
        db.query(Order)
        .filter(Order.id == payment.order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(404, "Order not found.")
    if order.status != OrderStatus.PAYMENT_PENDING:
        raise HTTPException(400, f"Order status is {order.status.value}, cannot pay.")
    if Decimal(str(payment.amount)) != Decimal(str(order.total_amount)):
        raise HTTPException(400, "Payment amount mismatch detected.")

    # Resolve shop user_id
    shop = db.query(Shop).filter(Shop.id == order.shop_id).first()
    if not shop:
        raise HTTPException(404, "Shop not found.")

    try:
        payment.status         = "SUCCESS"
        payment.transaction_id = transaction_id
        payment.completed_at   = datetime.now(timezone.utc)

        WalletService.process_order_payment(
            db=db,
            customer_id=order.customer_id,
            shop_user_id=shop.user_id,
            total_amount=Decimal(str(payment.amount)),
            order_id=order.id,
            idempotency_key=f"gateway-{transaction_id}",
        )

        order.status = OrderStatus.CREATED
        db.commit()
        logger.info(
            "payment.success payment=%d order=%d txn=%s",
            payment.id, order.id, transaction_id,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception:
        db.rollback()
        logger.exception("payment.success.error payment=%d", payment_id)
        raise HTTPException(500, "Payment processing failed.")

    return {
        "message":      "Payment successful.",
        "payment_id":   payment.id,
        "order_status": order.status.value,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /payment/failed
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/failed")
def payment_failed(
    payment_id:   int,
    reason:       str | None = None,
    current_user: User       = Depends(require_roles(["customer"])),
    db:           Session    = Depends(get_db),
):
    payment = (
        db.query(Payment)
        .filter(
            Payment.id == payment_id,
            Payment.user_id == current_user.id,
            Payment.status == "INITIATED",
        )
        .first()
    )
    if not payment:
        raise HTTPException(404, "Payment not found.")

    payment.status         = "FAILED"
    payment.failure_reason = reason
    payment.completed_at   = datetime.now(timezone.utc)

    order = db.query(Order).filter(Order.id == payment.order_id).first()
    if order:
        order.status = OrderStatus.CANCELLED

    db.commit()
    logger.info("payment.failed payment=%d reason=%s", payment.id, reason)
    return {"message": "Payment marked as failed.", "payment_id": payment.id}


# ─────────────────────────────────────────────────────────────────────────────
# POST /payment/{id}/refund
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{payment_id}/refund")
def refund_payment(
    payment_id: int,
    admin:      User    = Depends(require_admin),
    db:         Session = Depends(get_db),
):
    """
    Admin-initiated full refund.
    Reverses the order payment through the ledger (DR shop, CR customer).
    """
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .with_for_update()
        .first()
    )
    if not payment:
        raise HTTPException(404, "Payment not found.")
    if payment.status != "SUCCESS":
        raise HTTPException(400, f"Payment is {payment.status}, cannot refund.")

    order = (
        db.query(Order)
        .filter(Order.id == payment.order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(404, "Order not found.")

    shop = db.query(Shop).filter(Shop.id == order.shop_id).first()
    if not shop:
        raise HTTPException(404, "Shop not found.")

    # Get commission rate at time of original payment
    from app.models.commission import CommissionConfig
    commission_config = (
        db.query(CommissionConfig)
        .filter(CommissionConfig.is_active == True)  # noqa: E712
        .order_by(CommissionConfig.created_at.desc())
        .first()
    )
    commission_pct = Decimal(str(commission_config.percent)) if commission_config else Decimal("0.00")

    try:
        WalletService.process_refund(
            db=db,
            customer_id=order.customer_id,
            shop_user_id=shop.user_id,
            total_amount=Decimal(str(payment.amount)),
            order_id=order.id,
            commission_pct=commission_pct,
            idempotency_key=f"refund-payment-{payment_id}",
        )

        payment.status      = "REFUNDED"
        payment.refunded_at = datetime.now(timezone.utc)
        order.status        = OrderStatus.CANCELLED

        db.commit()
        logger.info("payment.refunded payment=%d by admin=%d", payment_id, admin.id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception:
        db.rollback()
        logger.exception("payment.refund.error payment=%d", payment_id)
        raise HTTPException(500, "Refund failed.")

    return {"message": "Payment refunded successfully.", "payment_id": payment.id}
