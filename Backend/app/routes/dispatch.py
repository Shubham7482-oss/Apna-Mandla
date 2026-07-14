from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Union
from pydantic import BaseModel

from app.core.database import get_db
from app.models.order import Order, OrderStatus
from app.models.parcel import Parcel, ParcelStatus
from app.schemas.order import OrderResponse as OrderSchema
from app.schemas.parcel import Parcel as ParcelSchema
from app.models.user import User
from app.core.auth import get_current_user, require_roles
from app.services.location_service import get_distance_between_plus_codes

router = APIRouter()

class Delivery(BaseModel):
    type: str
    data: Union[OrderSchema, ParcelSchema]
    distance: float

@router.get("/rider/deliveries", response_model=List[Delivery])
def get_available_deliveries(db: Session = Depends(get_db), current_user: User = Depends(require_roles(["rider"]))):
    if not current_user.rider_profile or not current_user.rider_profile.current_plus_code:
        raise HTTPException(status_code=400, detail="Rider has no location set")

    rider_plus_code = current_user.rider_profile.current_plus_code

    available_orders = db.query(Order).filter(
        Order.status.in_([OrderStatus.READY_FOR_PICKUP, OrderStatus.BROADCASTING])
    ).all()

    available_parcels = db.query(Parcel).filter(
        Parcel.status == ParcelStatus.SEARCHING_FOR_RIDER
    ).all()

    deliveries = []

    for order in available_orders:
        shop_plus_code = order.shop.profile.plus_code
        if shop_plus_code:
            distance = get_distance_between_plus_codes(rider_plus_code, shop_plus_code)
            deliveries.append(Delivery(type="order", data=OrderSchema.from_orm(order), distance=distance))

    for parcel in available_parcels:
        if parcel.pickup_plus_code:
            distance = get_distance_between_plus_codes(rider_plus_code, parcel.pickup_plus_code)
            deliveries.append(Delivery(type="parcel", data=ParcelSchema.from_orm(parcel), distance=distance))

    deliveries.sort(key=lambda d: d.distance)

    return deliveries

@router.post("/rider/deliveries/accept")
def accept_delivery(delivery_type: str = Body(...), delivery_id: int = Body(...), db: Session = Depends(get_db), current_user: User = Depends(require_roles(["rider"]))):
    with db.begin():
        if delivery_type == "order":
            delivery = db.query(Order).with_for_update().filter(Order.id == delivery_id).first()
            if not delivery or delivery.status not in [OrderStatus.READY_FOR_PICKUP, OrderStatus.BROADCASTING]:
                raise HTTPException(status_code=404, detail="Order not available for pickup")
            delivery.status = OrderStatus.RIDER_ASSIGNED
            delivery.assigned_rider_id = current_user.rider_profile.id
        elif delivery_type == "parcel":
            delivery = db.query(Parcel).with_for_update().filter(Parcel.id == delivery_id).first()
            if not delivery or delivery.status != ParcelStatus.SEARCHING_FOR_RIDER:
                raise HTTPException(status_code=404, detail="Parcel not available for pickup")
            delivery.status = ParcelStatus.ASSIGNED
            # This assumes the order related to the parcel has the rider assignment info
            order = db.query(Order).filter(Order.id == delivery.order_id).first()
            if order:
                order.assigned_rider_id = current_user.rider_profile.id
        else:
            raise HTTPException(status_code=400, detail="Invalid delivery type")

        db.commit()

    return {"message": "Delivery accepted successfully"}
