from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.routes.admin_permission import require_permission
from app.models.order import Order
from app.models.payment import Payment

router = APIRouter(prefix="/admin/orders", tags=["Admin Orders"])


# ───────────────────────────────
# ADMIN → LIST ALL ORDERS
# ───────────────────────────────
@router.get("")
def list_orders(
    status_filter: str | None = None,
    current_admin = Depends(require_permission("orders", "view")),
    db: Session = Depends(get_db),
):
    q = db.query(Order).filter(Order.is_archived == False)

    if status_filter:
        q = q.filter(Order.status == status_filter)

    orders = q.order_by(Order.created_at.desc()).all()

    return [
        {
            "order_id": o.id,
            "status": o.status,
            "customer_id": o.customer_id,
            "shop_id": o.shop_id,
            "rider_id": o.rider_id,
            "created_at": o.created_at,
        }
        for o in orders
    ]


# ───────────────────────────────
# ADMIN → VIEW ORDER DETAILS
# ───────────────────────────────
@router.get("/{order_id}")
def order_detail(
    order_id: int,
    current_admin = Depends(require_permission("orders", "view")),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.is_archived == False)
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    payment = (
        db.query(Payment)
        .filter(Payment.order_id == order.id, Payment.status == "SUCCESS")
        .first()
    )

    return {
        "order_id": order.id,
        "status": order.status,
        "customer_id": order.customer_id,
        "shop_id": order.shop_id,
        "rider_id": order.rider_id,
        "payment_status": payment.status if payment else "UNPAID",
        "created_at": order.created_at,
    }


# ───────────────────────────────
# ADMIN → FORCE CANCEL ORDER
# ───────────────────────────────
@router.post("/{order_id}/force-cancel")
def force_cancel(
    order_id: int,
    reason: str | None = None,
    current_admin = Depends(require_permission("orders", "approve")),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.is_archived == False)
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = "CANCELLED"
    order.cancelled_at = datetime.utcnow()
    order.cancel_reason = reason

    payment = (
        db.query(Payment)
        .filter(Payment.order_id == order.id, Payment.status == "SUCCESS")
        .first()
    )

    if payment:
        payment.status = "REFUNDED"
        payment.refunded_at = datetime.utcnow()

    db.commit()

    return {
        "message": "Order force-cancelled",
        "order_id": order.id,
    }


# ───────────────────────────────
# ADMIN → FORCE ASSIGN RIDER
# ───────────────────────────────
@router.post("/{order_id}/assign-rider")
def force_assign_rider(
    order_id: int,
    rider_id: int,
    current_admin = Depends(require_permission("orders", "approve")),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.status == "READY",
            Order.is_archived == False,
        )
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not assignable")

    order.rider_id = rider_id
    order.status = "PICKED"
    order.picked_at = datetime.utcnow()

    db.commit()

    return {
        "message": "Rider assigned",
        "order_id": order.id,
        "rider_id": rider_id,
    }