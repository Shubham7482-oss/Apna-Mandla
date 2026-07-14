from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.order_item import OrderItem
from app.models.shop import Shop

router = APIRouter(prefix="/logistics", tags=["Logistics & QR"])

@router.post("/item-pickup-scan")
def scan_and_pickup_item(
    order_id: int,
    shop_id: int, # QR scan se jo shop_id milegi
    item_ids: List[int], # Jo items us dukan se liye
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 1. Shop ki branding details nikalo (Subscription Check)
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(404, "Dukan ki jankari nahi mili")

    # Subscription logic: Pro hai toh Name, warna Random Partner ID
    display_name = (
        shop.custom_display_name 
        if shop.is_subscribed and shop.custom_display_name 
        else f"Apna Mandla Partner {shop.random_id_name}"
    )

    # 2. Check karo ki ye items isi order ke hain?
    items = db.query(OrderItem).filter(
        OrderItem.order_id == order_id,
        OrderItem.id.in_(item_ids)
    ).all()

    if not items:
        raise HTTPException(400, "In items ka record nahi mila ya ye order galat hai.")

    # 3. Update Status & Shop Linking (More efficient bulk update)
    item_ids_to_update = [item.id for item in items]
    db.query(OrderItem).filter(
        OrderItem.id.in_(item_ids_to_update)
    ).update({
        'shop_id': shop_id,
        'pickup_status': "PICKED",
        'picked_at': datetime.now(timezone.utc), # Use UTC for all timestamps
        'is_shop_confirmed': False
    }, synchronize_session=False)

    db.commit()

    return {
        "status": "success",
        "message": f"Items successfully picked from {display_name}.",
        "shop_name_shown": display_name,
        "is_premium_shop": shop.is_subscribed,
        "next_step": "Please ask the shopkeeper to confirm the pickup on their app."
    }