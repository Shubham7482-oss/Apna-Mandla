from datetime import datetime
from sqlalchemy.orm import Session
from app.models.order import Order
from app.models.rider import Rider

COD_LIMIT = 2000


def get_available_orders_for_rider(db: Session, rider: Rider):

    # Rider must be free
    if rider.current_order_id:
        return []

    now = datetime.utcnow()

    # Base query: active broadcasts only
    orders = (
        db.query(Order)
        .filter(
            Order.status == "BROADCASTING",
            Order.broadcast_deadline != None,
            Order.broadcast_deadline > now,
        )
        .all()
    )

    filtered_orders = []

    for order in orders:

        # COD eligibility check
        if order.payment_mode == "COD":

            if rider.is_on_probation:
                continue

            if rider.is_cod_blocked:
                continue

            order_amount = get_order_amount(order)

            if rider.cod_liability + order_amount > COD_LIMIT:
                continue

        filtered_orders.append(order)

    return filtered_orders


def get_order_amount(order: Order):
    # Replace with real total calculation
    return sum(item.quantity * item.price for item in order.items)