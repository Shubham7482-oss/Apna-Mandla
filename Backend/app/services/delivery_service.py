from fastapi import HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal

from app.models.order import Order
from app.models.rider import Rider
from app.models.otp import OTP

from app.services.ledger_service import LedgerService
from app.services.udhar_service import add_udhar_debit   # ✅ NEW


COD_LIMIT = Decimal("2000.00")
DELIVERY_FEE = Decimal("30.00")  # later move to config


def complete_delivery(
    db: Session,
    rider_id: int,
    order_id: int,
    otp_code: str
):

    # 🔒 Lock order row
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # 🔒 Lock rider
    rider = (
        db.query(Rider)
        .filter(Rider.id == rider_id)
        .with_for_update()
        .first()
    )

    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")

    if order.assigned_rider_id != rider.rider_profile_id:
        raise HTTPException(status_code=403, detail="Not your order")

    if order.status != "OUT_FOR_DELIVERY":
        raise HTTPException(status_code=400, detail="Invalid order state")

    # 🔐 OTP VERIFY
    otp = (
        db.query(OTP)
        .filter(
            OTP.order_id == order.id,
            OTP.code == otp_code,
            OTP.is_used == False
        )
        .with_for_update()
        .first()
    )

    if not otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    otp.is_used = True

    # =====================================================
    # 💰 HANDLE COD LIABILITY
    # =====================================================
    if order.payment_mode == "COD":

        order_amount = Decimal(str(get_order_amount(order)))

        if rider.cod_liability + order_amount > COD_LIMIT:
            raise HTTPException(status_code=400, detail="COD limit exceeded")

        rider.cod_liability += order_amount

        if rider.cod_liability >= COD_LIMIT:
            rider.is_cod_blocked = True

    # =====================================================
    # 💳 HANDLE UDHAAR (NEW BLOCK)
    # =====================================================
    if order.payment_mode == "UDHAR":

        order_amount = Decimal(str(get_order_amount(order)))

        add_udhar_debit(
            db=db,
            shop_id=order.shop_id,
            customer_id=order.customer_id,
            order_id=order.id,
            amount=order_amount,
        )

    # =====================================================
    # 💰 CREDIT DELIVERY FEE (LEDGER BASED)
    # =====================================================
    LedgerService.credit_rider_delivery_fee(
        db=db,
        rider_id=rider.id,
        amount=DELIVERY_FEE,
        order_id=order.id
    )

    # =====================================================
    # UPDATE ORDER STATE
    # =====================================================
    order.status = "DELIVERED"
    order.delivered_at = datetime.utcnow()

    # =====================================================
    # RELEASE RIDER
    # =====================================================
    rider.current_order_id = None
    rider.completed_orders_count += 1

    if rider.completed_orders_count >= 10:
        rider.is_on_probation = False

    db.commit()
    db.refresh(order)

    return order


# ============================================================
# HELPER
# ============================================================

def get_order_amount(order: Order):
    return sum(
        Decimal(str(item.quantity)) * Decimal(str(item.price))
        for item in order.items
    )