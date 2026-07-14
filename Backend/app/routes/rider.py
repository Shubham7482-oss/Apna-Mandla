from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.rider import Rider
from app.models.user import User
from app.models.order import Order
from pydantic import BaseModel

# Services
from app.services.rider_assignment_service import accept_order
from app.services.delivery_service import complete_delivery
from app.services.cod_settlement_service import settle_cod
from app.services.rider_broadcast_query_service import get_available_orders_for_rider
from app.websocket_manager import manager

router = APIRouter(prefix="/rider", tags=["Rider"])

class LocationUpdate(BaseModel):
    latitude: float
    longitude: float
    order_id: int

# ──────────────────────────────────────────────────────────
# 🛠️ HELPER: GET RIDER PROFILE (Multi-role support)
# ──────────────────────────────────────────────────────────
def get_rider_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Check if user has a Rider profile, regardless of their current 'user_type'.
    This allows a Customer to act as a Rider if they are registered.
    """
    rider = db.query(Rider).filter(
        Rider.user_id == current_user.id,
        Rider.is_archived == False
    ).first()
    
    if not rider:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Aap Rider ke roop mein registered nahi hain. Please register first."
        )
    return rider

# ──────────────────────────────────────────────────────────
# 🚀 RIDER ROUTES
# ──────────────────────────────────────────────────────────

@router.post("/location")
async def update_rider_location(
    location: LocationUpdate,
    rider: Rider = Depends(get_rider_profile),
    db: Session = Depends(get_db)
):
    """Update rider's location and broadcast it to the customer and shop."""
    order = db.query(Order).filter(Order.id == location.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Authorization: Ensure rider is assigned to this order
    if order.assigned_rider_id != rider.id:
        raise HTTPException(status_code=403, detail="Not authorized for this order")

    location_data = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "order_id": location.order_id
    }

    # Send location to customer
    await manager.send_personal_message(location_data, str(order.customer_id))

    # Send location to shop owner
    if order.shop and order.shop.owner:
        await manager.send_personal_message(location_data, str(order.shop.owner.id))

    return {"message": "Location updated"}

@router.get("/me")
def get_my_rider(rider: Rider = Depends(get_rider_profile)):
    # Ab code chota aur saaf hai
    return rider

@router.get("/available-orders")
def rider_available_orders(
    rider: Rider = Depends(get_rider_profile), 
    db: Session = Depends(get_db)
):
    # ✅ Optimization: Only show orders if rider is ONLINE
    if not rider.is_online:
        return {"message": "Please go online to see orders", "orders": []}

    orders = get_available_orders_for_rider(db, rider)
    return [
        {
            "order_id": o.id,
            "shop_id": o.shop_id,
            "shop_name": o.shop.profile.name if o.shop.profile else "Dukan",
            "payment_mode": o.payment_mode,
            "total_amount": o.total_amount,
            "distance": "Calculate kar sakte hain logic se"
        }
        for o in orders
    ]

@router.post("/orders/{order_id}/accept")
def rider_accept_order(
    order_id: int, 
    rider: Rider = Depends(get_rider_profile), 
    db: Session = Depends(get_db)
):
    order = accept_order(db=db, rider_id=rider.id, order_id=order_id)
    return {"message": "Order utha liya gaya hai!", "order_id": order.id}

@router.post("/orders/{order_id}/complete")
def rider_complete_order(
    order_id: int, 
    otp_code: str, 
    rider: Rider = Depends(get_rider_profile), 
    db: Session = Depends(get_db)
):
    # Delivery complete karne ke liye Customer se OTP lena zaroori hai (Security)
    order = complete_delivery(db=db, rider_id=rider.id, order_id=order_id, otp_code=otp_code)
    return {"message": "Delivery safalta purvak sampann hui!", "order_id": order.id}

@router.post("/toggle-status")
def toggle_online_status(
    rider: Rider = Depends(get_rider_profile), 
    db: Session = Depends(get_db)
):
    """Rider ko Online/Offline karne ke liye"""
    rider.is_online = not rider.is_online
    db.commit()
    return {"is_online": rider.is_online}