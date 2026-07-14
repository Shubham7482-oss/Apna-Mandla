from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timedelta
import math
import asyncio

from app.models.order import Order
from app.models.rider import Rider
from app.models.rider_profile import RiderProfile
from app.core.database import SessionLocal

COD_LIMIT = 2000
MAX_RADIUS_KM = 20


def accept_order(db: Session, rider_id: int, order_id: int):

    # Lock order row (important)
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # ===============================
    # BROADCAST EXPIRY CHECK (NEW)
    # ===============================
    if (
        order.status == "BROADCASTING"
        and order.broadcast_deadline
        and datetime.utcnow() > order.broadcast_deadline
    ):
        order.status = "READY_FOR_PICKUP"
        order.broadcast_deadline = None
        db.commit()
        raise HTTPException(status_code=400, detail="Broadcast expired")

    if order.assigned_rider_id:
        raise HTTPException(status_code=400, detail="Order already assigned")

    if order.status != "BROADCASTING":
        raise HTTPException(status_code=400, detail="Order not available")

    rider = db.query(RiderProfile).filter(RiderProfile.id == rider_id).first()

    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")

    # In a real app, check if rider has an active order
    # Assuming rider_profiles has a relationship or field for current status

    if rider.blacklisted:
        raise HTTPException(status_code=403, detail="Rider blacklisted")

    if not rider.kyc_verified:
        raise HTTPException(status_code=403, detail="KYC not completed")

    # ===============================
    # COD GUARD
    # ===============================
    if order.payment_mode == "COD":
        # Simplified COD logic for example
        pass

    # ===============================
    # ASSIGN RIDER
    # ===============================
    order.assigned_rider_id = rider.id
    order.status = "RIDER_ASSIGNED"
    order.broadcast_deadline = None

    db.commit()
    db.refresh(order)

    return order


def start_order_broadcast(db: Session, order: Order):
    """
    Initializes the broadcast for an order.
    Starts with a 2km radius.
    """
    order.status = "BROADCASTING"
    order.broadcast_radius = 2
    # Set a total timeout for the broadcast (e.g., 10 minutes)
    order.broadcast_deadline = datetime.utcnow() + timedelta(minutes=10)
    db.commit()
    
    # Trigger initial notification logic here
    _notify_riders_in_radius(db, order)


async def expand_radius_and_notify(order_id: int):
    """
    Asynchronous task that increases the broadcast radius every minute
    and notifies riders until assigned or max radius reached.
    """
    while True:
        await asyncio.sleep(60)  # Wait for 1 minute
        
        db = SessionLocal()
        try:
            order = db.query(Order).filter(Order.id == order_id).first()
            
            # Stop if order is no longer broadcasting (e.g., assigned or cancelled)
            if not order or order.status != "BROADCASTING":
                break

            if order.broadcast_radius >= MAX_RADIUS_KM:
                # Optionally mark as failed/ready_for_pickup if no rider found
                order.status = "READY_FOR_PICKUP"
                order.broadcast_deadline = None
                db.commit()
                break

            # Increase radius by 2km each minute
            order.broadcast_radius += 2
            db.commit()

            # Notify riders in the new expanded radius
            _notify_riders_in_radius(db, order)
            
        except Exception as e:
            print(f"Error in broadcast loop for order {order_id}: {e}")
            break
        finally:
            db.close()


def _notify_riders_in_radius(db: Session, order: Order):
    """
    Finds available riders within the order's current broadcast_radius
    relative to the shop's location and sends notifications.
    """
    shop_profile = order.shop.profile
    if not shop_profile or not shop_profile.latitude or not shop_profile.longitude:
        return

    lat1, lon1 = shop_profile.latitude, shop_profile.longitude
    radius = order.broadcast_radius

    # Query active, verified, non-blacklisted riders
    riders = db.query(RiderProfile).filter(
        RiderProfile.is_active == True,
        RiderProfile.kyc_verified == True,
        RiderProfile.blacklisted == False
    ).all()

    notified_count = 0
    for rider in riders:
        if rider.latitude and rider.longitude:
            distance = _calculate_distance(lat1, lon1, rider.latitude, rider.longitude)
            if distance <= radius:
                # Actual notification logic would go here (e.g. Firebase, Websocket)
                # For now we simulate the trigger
                from app.services.broadcast_service import notify_rider_of_order
                notify_rider_of_order(rider.user_id, order.id, radius)
                notified_count += 1
    
    return notified_count


def _calculate_distance(lat1, lon1, lat2, lon2):
    """Haversine formula to calculate distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_order_amount(order: Order):
    return sum(item.quantity * item.price_at_order for item in order.items)