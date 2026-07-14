from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.rbac import require_rider, require_shop
from app.models.order import Order, OrderStatus, PaymentMode
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.services.ledger_service import LedgerService
from decimal import Decimal
import random

router = APIRouter(prefix="/order-flow", tags=["Order Lifecycle"])

@router.post("/ready-for-pickup/{order_id}")
def mark_ready(order_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_shop)):
    """Shopkeeper marks order as ready. System starts broadcasting to riders."""
    order = db.query(Order).filter(Order.id == order_id, Order.shop_id == current_user.owned_shop[0].id).first()
    if not order: raise HTTPException(404, "Order not found")
    
    order.status = OrderStatus.BROADCASTING
    # Generate Delivery OTP
    order.delivery_otp = str(random.randint(100000, 999999))
    db.commit()
    return SuccessResponse(success=True, message="Order is now broadcasting to nearby riders.")

@router.get("/available-tasks")
def get_broadcasted_tasks(db: Session = Depends(get_db), current_user: User = Depends(require_rider)):
    """Rider sees orders looking for delivery in their area."""
    rider_profile = current_user.rider_profile
    
    # Tier Logic: NORMAL riders can't see COD orders
    query = db.query(Order).filter(
        Order.status == OrderStatus.BROADCASTING,
        Order.mandla_id == rider_profile.mandla_id
    )
    
    if rider_profile.verification_tier != "FULL":
        query = query.filter(Order.payment_mode != PaymentMode.COD)
        
    return query.all()

@router.post("/accept-task/{order_id}")
def accept_task(order_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_rider)):
    """Rider accepts a broadcasting order."""
    order = db.query(Order).filter(Order.id == order_id, Order.status == OrderStatus.BROADCASTING).with_for_update().first()
    if not order: raise HTTPException(400, "Order no longer available")
    
    order.assigned_rider_id = current_user.rider_profile.id
    order.status = OrderStatus.RIDER_ASSIGNED
    db.commit()
    return SuccessResponse(success=True, message="Task assigned to you!")

@router.post("/complete-order/{order_id}")
def complete_order(
    order_id: int,
    otp: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_rider)
):
    """Rider completes the delivery by providing the customer's OTP."""
    order = db.query(Order).filter(
        Order.id == order_id, 
        Order.assigned_rider_id == current_user.rider_profile.id
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found or not assigned to you")

    # 1. Verify OTP
    if order.delivery_otp != otp:
        raise HTTPException(status_code=400, detail="Invalid Delivery OTP")

    # 2. Financial Settlement (Payouts)
    # total_amount = subtotal - discount + delivery_fee
    # Shop gets: subtotal - discount - platform_commission
    # Rider gets: delivery_fee
    
    try:
        # Payout to Shop
        shop_owner_id = order.shop.user_id
        shop_payout = order.subtotal - order.discount_amount
        LedgerService.record_transaction(
            db, shop_owner_id, shop_payout, "CREDIT", 
            f"Payout for Order #{order.id}", order.id
        )

        # Payout to Rider
        rider_user_id = current_user.id
        rider_payout = order.delivery_fee
        LedgerService.record_transaction(
            db, rider_user_id, rider_payout, "CREDIT", 
            f"Delivery Fee for Order #{order.id}", order.id
        )

        # 3. Mark Delivered
        order.status = OrderStatus.DELIVERED
        db.commit()
        
        return SuccessResponse(success=True, message="Order delivered and payouts settled!")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Settlement failed: {str(e)}")