from fastapi import HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal
from datetime import datetime

from app.models.order import Order
from app.models.rider import Rider
from app.models.otp import OTP

from app.services.ledger_service import (
    get_or_create_wallet,
    _create_ledger_entry,
    ADMIN_ENTITY_TYPE,
    ADMIN_ENTITY_ID,
    RIDER_ENTITY_TYPE,
)

TRANSFER_PENALTY = Decimal("50.00")


def transfer_order(
    db: Session,
    rider_id: int,
    order_id: int,
    otp_code: str | None = None,
):

    # 🔒 Lock order
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.assigned_rider_id != rider_id:
        raise HTTPException(status_code=403, detail="Not your order")

    if order.status not in ["RIDER_ASSIGNED", "OUT_FOR_DELIVERY"]:
        raise HTTPException(status_code=400, detail="Cannot transfer now")

    # 🔒 Lock rider
    rider = (
        db.query(Rider)
        .filter(Rider.id == rider_id)
        .with_for_update()
        .first()
    )

    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")

    # =====================================================
    # CASE 1: BEFORE PARCEL PICKUP (FREE TRANSFER)
    # =====================================================
    if order.status == "RIDER_ASSIGNED" and order.transfer_count == 0:

        order.assigned_rider_id = None
        order.status = "BROADCASTING"
        order.transfer_count += 1

        rider.current_order_id = None

        db.commit()
        return {"message": "Order transferred (free)"}

    # =====================================================
    # CASE 2: AFTER PICKUP (PENALTY REQUIRED)
    # =====================================================
    if order.status == "OUT_FOR_DELIVERY":

        if not otp_code:
            raise HTTPException(status_code=400, detail="OTP required")

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

        # Check wallet balance for penalty
        rider_wallet = get_or_create_wallet(
            db,
            RIDER_ENTITY_TYPE,
            rider.id
        )

        if rider_wallet.balance < TRANSFER_PENALTY:
            raise HTTPException(status_code=400, detail="Insufficient balance for penalty")

        admin_wallet = get_or_create_wallet(
            db,
            ADMIN_ENTITY_TYPE,
            ADMIN_ENTITY_ID
        )

        # Ledger Penalty Transfer
        _create_ledger_entry(
            db,
            rider_wallet,
            "DEBIT",
            TRANSFER_PENALTY,
            order.id,
            "Order Transfer Penalty",
        )

        _create_ledger_entry(
            db,
            admin_wallet,
            "CREDIT",
            TRANSFER_PENALTY,
            order.id,
            "Transfer Penalty Received",
        )

        # Reset order
        order.assigned_rider_id = None
        order.status = "BROADCASTING"
        order.transfer_count += 1

        rider.current_order_id = None

        db.commit()

        return {"message": "Order transferred with penalty"}

    raise HTTPException(status_code=400, detail="Transfer not allowed")