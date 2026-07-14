from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.rating_service import RatingService

router = APIRouter(prefix="/ratings", tags=["Ratings"])


@router.post("/rate")
def create_rating(
    order_id: int,
    rating: int,
    target_type: Literal["SHOP", "RIDER", "CUSTOMER"],
    target_id: int,
    comment: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generic rating endpoint (3‑way, verified):
    - Customer → SHOP, RIDER
    - Rider    → SHOP, CUSTOMER
    - Seller   → RIDER, CUSTOMER
    """
    return RatingService.create_rating(
        db=db,
        order_id=order_id,
        actor=current_user,
        rating_value=rating,
        target_type=target_type,
        target_id=target_id,
        comment=comment,
    )


@router.get("/summary/{target_id}")
def get_rating_summary(
    target_id: int,
    target_type: Literal["SHOP", "RIDER", "CUSTOMER"],
    db: Session = Depends(get_db),
):
    """
    Get average rating and star distribution for any entity.
    """
    return RatingService.get_rating_summary(db, target_id, target_type)
