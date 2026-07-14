from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Any

from app.core.database import get_db
from app.core.rbac import require_roles
from app.core.feature_guard import check_feature_access

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.shop import Shop
from app.models.payment import Payment
from app.models.user import User

router = APIRouter(prefix="/shop/orders", tags=["Shop Orders"])


# ───────────────────────────────
# INTERNAL: GET SHOP BY OWNER
# ───────────────────────────────
def _get_my_shop(db: Session, current_user: User) -> Shop:
    shop = (
        db.query(Shop)
        .filter(
            Shop.user_id == current_user.id,
            Shop.is_archived == False,
        )
        .first()
    )

    if not shop:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized as shop owner",
        )

    return shop


# ───────────────────────────────
# SHOP → LIST ALL ORDERS
# ───────────────────────────────
@router.get("/")
def list_shop_orders(
    current_user: User = Depends(require_roles(["shop"])),
    db: Session = Depends(get_db),
):
    shop = _get_my_shop(db, current_user)

    orders = (
        db.query(Order)
        .filter(Order.shop_id == shop.id, Order.is_archived == False)
        .order_by(Order.created_at.desc())
        .all()
    )

    result = []
    for order in orders:
        items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        result.append({
            "order_id": order.id,
            "customer_id": order.customer_id,
            "status": order.status,
            "total_amount": float(order.total_amount),
            "payment_mode": order.payment_mode,
            "delivery_address": order.delivery_address,
            "created_at": order.created_at,
            "items": [
                {
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "price_at_order": float(item.price_at_order)
                } for item in items
            ]
        })

    return result


# ───────────────────────────────
# SHOP → ACCEPT ORDER
# ───────────────────────────────
@router.post("/{order_id}/accept")
def accept_order(
    order_id: int,
    current_user: User = Depends(require_roles(["shop"])),
    db: Session = Depends(get_db),
):
    shop = _get_my_shop(db, current_user)

    # 🔒 PREMIUM CHECK
    if not check_feature_access(shop):
        raise HTTPException(
            status_code=403,
            detail="Order processing requires Premium subscription.",
        )

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.shop_id == shop.id,
            Order.status == "CREATED",
            Order.is_archived == False,
        )
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found or not in CREATED status",
        )

    order.status = "ACCEPTED"
    order.accepted_at = datetime.utcnow()
    db.commit()

    return {"message": "Order accepted successfully"}


# ───────────────────────────────
# SHOP → MARK ORDER PREPARING (PREMIUM ONLY)
# ───────────────────────────────
@router.post("/{order_id}/prepare")
def mark_preparing(
    order_id: int,
    current_user: User = Depends(require_roles(["shop"])),
    db: Session = Depends(get_db),
):
    shop = _get_my_shop(db, current_user)

    # 🔒 PREMIUM CHECK
    if not check_feature_access(shop):
        raise HTTPException(
            status_code=403,
            detail="Order processing requires Premium subscription.",
        )

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.shop_id == shop.id,
            Order.status == "ACCEPTED",
            Order.is_archived == False,
        )
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found or not allowed",
        )

    # 🔐 PAYMENT MUST BE SUCCESS OR COD
    if order.payment_mode == "PREPAID":
        payment = (
            db.query(Payment)
            .filter(
                Payment.order_id == order.id,
                Payment.status == "SUCCESS",
            )
            .first()
        )

        if not payment:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Payment not completed",
            )

    order.status = "PREPARING"
    order.preparing_at = datetime.utcnow()
    db.commit()

    return {"message": "Order marked as preparing"}


# ───────────────────────────────
# SHOP → MARK ORDER READY (PREMIUM ONLY)
# ───────────────────────────────
@router.post("/{order_id}/ready")
def mark_ready(
    order_id: int,
    current_user: User = Depends(require_roles(["shop"])),
    db: Session = Depends(get_db),
):
    shop = _get_my_shop(db, current_user)

    # 🔒 PREMIUM CHECK
    if not check_feature_access(shop):
        raise HTTPException(
            status_code=403,
            detail="Order processing requires Premium subscription.",
        )

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.shop_id == shop.id,
            Order.status == "PREPARING",
            Order.is_archived == False,
        )
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found or not allowed",
        )

    order.status = "READY"
    order.ready_at = datetime.utcnow()
    db.commit()

    return {"message": "Order marked as ready"}