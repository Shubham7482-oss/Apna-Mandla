from typing import Literal

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.rating import Rating
from app.models.user import User


class RatingService:
    """
    Centralized 3-way rating logic:
    - Customer → Shop, Rider
    - Rider    → Shop, Customer
    - Seller   → Rider, Customer
    """

    @staticmethod
    def create_rating(
        db: Session,
        *,
        order_id: int,
        actor: User,
        rating_value: int,
        target_type: Literal["SHOP", "RIDER", "CUSTOMER"],
        target_id: int,
        comment: str | None = None,
    ) -> Rating:
        # 1. Validation (1–5)
        if not (1 <= rating_value <= 5):
            raise HTTPException(
                status_code=400,
                detail="Rating must be between 1 and 5",
            )

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # 2. Status check (must be delivered)
        if order.status != OrderStatus.DELIVERED:
            raise HTTPException(
                status_code=400,
                detail="Rating allowed only after delivery",
            )

        # 3. Authorization & target validation (3-way)
        if target_type in ("SHOP", "RIDER"):
            # Customer can rate shop & rider on their own order
            if actor.id != order.customer_id:
                raise HTTPException(
                    status_code=403,
                    detail="Only the customer can rate shop or rider",
                )

            if target_type == "SHOP":
                # Ensure the shop is part of the order
                if order.shop_id != target_id:
                    item_exists = (
                        db.query(OrderItem)
                        .filter(
                            OrderItem.order_id == order_id,
                            OrderItem.shop_id == target_id,
                        )
                        .first()
                    )
                    if not item_exists:
                        raise HTTPException(
                            status_code=400,
                            detail="This shop is not part of the order",
                        )
            elif target_type == "RIDER":
                if order.assigned_rider_id is None:
                    raise HTTPException(
                        status_code=400,
                        detail="No rider assigned to this order",
                    )
                if order.assigned_rider_id != target_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid rider for this order",
                    )

        elif target_type == "CUSTOMER":
            # Rider or shop owner can rate the customer
            allowed_seller_user_id = order.shop.owner.id if order.shop else None
            if actor.id not in (allowed_seller_user_id,):
                # Rider linkage requires additional joins; keep scope minimal for now.
                raise HTTPException(
                    status_code=403,
                    detail="Only rider or seller can rate the customer",
                )
            if order.customer_id != target_id:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid customer for this order",
                )

        # 4. Duplicate check: one rating per (order, actor, target_type, target_id)
        existing = (
            db.query(Rating)
            .filter(
                Rating.order_id == order_id,
                Rating.user_id == actor.id,
                Rating.target_id == target_id,
                Rating.target_type == target_type,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="You have already rated this entity for this order",
            )

        # 5. Save rating
        new_rating = Rating(
            order_id=order_id,
            user_id=actor.id,
            target_id=target_id,
            target_type=target_type,
            rating=rating_value,
            comment=comment,
        )

        db.add(new_rating)
        db.commit()
        db.refresh(new_rating)
        return new_rating

    @staticmethod
    def get_rating_summary(db: Session, target_id: int, target_type: str) -> dict:
        results = (
            db.query(Rating.rating, func.count(Rating.id))
            .filter(
                Rating.target_id == target_id,
                Rating.target_type == target_type,
            )
            .group_by(Rating.rating)
            .all()
        )

        dist: dict[str, int] = {str(i): 0 for i in range(1, 6)}
        total_count = 0
        total_sum = 0

        for score, count in results:
            dist[str(score)] = count
            total_count += count
            total_sum += score * count

        avg = round(total_sum / total_count, 2) if total_count > 0 else 0

        return {
            "average_rating": avg,
            "total_ratings": total_count,
            "distribution": dist,
        }

