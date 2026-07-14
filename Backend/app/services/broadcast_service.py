from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.order import Order


BROADCAST_WINDOW_SECONDS = 30


def start_broadcast(db: Session, order_id: int):

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != "READY_FOR_PICKUP":
        raise HTTPException(status_code=400, detail="Invalid order state")

    order.status = "BROADCASTING"
    order.broadcast_deadline = datetime.utcnow() + timedelta(
        seconds=BROADCAST_WINDOW_SECONDS
    )

    db.commit()
    db.refresh(order)

    return order


def expire_broadcast_if_needed(db: Session, order: Order):

    if order.status != "BROADCASTING":
        return

    if not order.broadcast_deadline:
        return

    if datetime.utcnow() > order.broadcast_deadline:
        order.status = "READY_FOR_PICKUP"
        order.broadcast_deadline = None
        db.commit()