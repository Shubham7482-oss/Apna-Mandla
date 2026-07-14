
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.core.auth import get_current_user, require_roles
from app.models.order import Order, OrderStatus
from app.models.parcel import Parcel, ParcelStatus
from app.models.rider import Rider

router = APIRouter()

@router.post("/delivery/{order_id}/pickup", status_code=204)
def confirm_pickup(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _ = Depends(require_roles(["rider"])),
):
    """Confirm that the rider has picked up the order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    # Check if the current rider is assigned to this order
    if order.assigned_rider.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not assigned to this order.")

    if order.status != OrderStatus.RIDER_ASSIGNED:
        raise HTTPException(status_code=400, detail=f"Order is not in a state to be picked up. Current status: {order.status}")

    # Update statuses
    order.status = OrderStatus.OUT_FOR_DELIVERY
    if order.parcel:
        order.parcel.status = ParcelStatus.PICKED_UP
    
    db.commit()

    return

@router.post("/delivery/{order_id}/delivered", status_code=204)
def confirm_delivery(
    order_id: int,
    otp: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _ = Depends(require_roles(["rider"])),
):
    """Confirm that the rider has delivered the order after verifying OTP."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    # Check if the current rider is assigned to this order
    if order.assigned_rider.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not assigned to this order.")

    if order.status != OrderStatus.OUT_FOR_DELIVERY:
        raise HTTPException(status_code=400, detail=f"Order is not out for delivery. Current status: {order.status}")

    # Verify OTP
    if order.delivery_otp != otp:
        raise HTTPException(status_code=400, detail="Invalid delivery OTP.")

    # Update statuses
    order.status = OrderStatus.DELIVERED
    if order.parcel:
        order.parcel.status = ParcelStatus.DELIVERED

    # Unassign the rider from the current order
    rider = db.query(Rider).filter(Rider.user_id == current_user.id).first()
    if rider:
        rider.current_order_id = None
    
    db.commit()

    return

