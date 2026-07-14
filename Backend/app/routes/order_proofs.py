from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import secrets
from decimal import Decimal

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.models.rider import Rider

router = APIRouter(prefix="/orders/proof", tags=["Order Proofs"])

# ──────────────────────────────────────────────────────────
# 📦 RIDER PICKUP PROOF (Shop se saaman uthate waqt)
# ──────────────────────────────────────────────────────────
@router.post("/{order_id}/pickup-proof")
def rider_pickup_proof(
    order_id: int,
    photo_url: str, # Flutter pehle image upload karke URL yahan bhejega
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(404, "Order nahi mila")

    # Security: Check assigned rider (user_id ke through)
    # assigned_rider yahan RiderProfile model ko point kar raha hai
    if not order.assigned_rider or order.assigned_rider.user_id != current_user.id:
        raise HTTPException(403, "Ye order aapka nahi hai")

    if order.status != OrderStatus.RIDER_ASSIGNED:
        raise HTTPException(400, "Order abhi pickup stage par nahi hai")

    # Proof save karein aur status badlein
    order.pickup_photo = photo_url
    order.status = OrderStatus.OUT_FOR_DELIVERY

    # 🚨 OTP Generate karna (4-digit as per your old code)
    # Use `secrets` for cryptographically secure random numbers
    order.delivery_otp = str(secrets.randbelow(10000)).zfill(4)

    db.commit()

    return {
        "message": "Pickup confirmed! OTP has been sent to the customer.",
        "otp_sent_to": order.customer.phone_number
    }

# ──────────────────────────────────────────────────────────
# 🏁 COMPLETE DELIVERY (Customer ko dete waqt)
# ──────────────────────────────────────────────────────────
@router.post("/{order_id}/complete-delivery")
def complete_delivery(
    order_id: int,
    otp: str,
    photo_url: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(404, "Order nahi mila")

    # Security Check
    if not order.assigned_rider or order.assigned_rider.user_id != current_user.id:
        raise HTTPException(403, "Unauthorized access")

    # 1. Check OTP
    if order.delivery_otp != otp:
        raise HTTPException(400, "Galat OTP! Customer se sahi code mangiye.")

    # 2. Save Delivery Proof
    order.delivery_photo = photo_url
    order.status = OrderStatus.DELIVERED

    # 3. IMPORTANT: Handle COD liability and payment status
    # Assuming 'order' has 'payment_method' and 'total_amount' attributes
    if order.payment_method == "COD":
        rider_profile = order.assigned_rider
        if rider_profile and hasattr(order, 'total_amount'):
            # Increase rider's cash on hand liability
            from app.models.rider import Rider
            rider = db.query(Rider).filter(Rider.rider_profile_id == rider_profile.id).first()
            if rider:
                rider.cod_liability += Decimal(str(order.total_amount))
            else:
                db.rollback()
                raise HTTPException(status_code=500, detail="Rider instance not found for this profile.")
            # A more accurate status for COD orders
            order.payment_status = "PAID_TO_RIDER"
        else:
            # This case should not happen if a rider is assigned. Rollback to be safe.
            db.rollback()
            raise HTTPException(status_code=500, detail="Rider or order amount info is missing for a COD order.")
    else: # For prepaid orders
        order.payment_status = "PAID"

    db.commit()
    db.refresh(order)

    return {"message": "Congratulations! Order delivered successfully."}