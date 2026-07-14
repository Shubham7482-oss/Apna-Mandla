from fastapi import HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal
from datetime import datetime

from app.models.order import Order
from app.models.rider import Rider
from app.models.otp import OTP

import uuid
from app.services.ledger_service import WalletService, PLATFORM_USER_ID
from app.models.ledger_entry import TransactionPurpose

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
        rider_balance = WalletService.get_balance(db, rider.user_id)

        if rider_balance < TRANSFER_PENALTY:
            raise HTTPException(status_code=400, detail="Insufficient balance for penalty")

        # Ledger Penalty Transfer
        cid = str(uuid.uuid4())
        ik = f"transfer-penalty-{order.id}-{rider.id}"

        WalletService._debit(
            db=db,
            user_id=rider.user_id,
            amount=TRANSFER_PENALTY,
            transaction_type=TransactionPurpose.ADJUSTMENT,
            correlation_id=cid,
            description=f"Order #{order.id} Transfer Penalty",
            order_id=order.id,
            idempotency_key=f"{ik}-dr"
        )

        WalletService._credit(
            db=db,
            user_id=PLATFORM_USER_ID,
            amount=TRANSFER_PENALTY,
            transaction_type=TransactionPurpose.ADJUSTMENT,
            correlation_id=cid,
            description=f"Transfer Penalty Received from Rider #{rider.id}",
            order_id=order.id,
            idempotency_key=f"{ik}-cr"
        )

        # Reset order
        order.assigned_rider_id = None
        order.status = "BROADCASTING"
        order.transfer_count += 1

        rider.current_order_id = None

        db.commit()

        return {"message": "Order transferred with penalty"}

    raise HTTPException(status_code=400, detail="Transfer not allowed")