from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_roles

from app.models.subscription_plan import SubscriptionPlan
from app.models.user import User

router = APIRouter(prefix="/admin/subscription", tags=["Admin Subscription"])


# ───────────────────────────────
# ADMIN → CREATE PLAN
# ───────────────────────────────
@router.post("/create")
def create_plan(
    category_id: int,
    name: str,
    price: int,
    max_products: int = 10,
    max_discounts: int = 0,
    priority_weight: int = 1,
    current_user: User = Depends(require_roles(["admin"])),
    db: Session = Depends(get_db),
):

    plan = SubscriptionPlan(
        category_id=category_id,
        name=name,
        price=price,
        max_products=max_products,
        max_discounts=max_discounts,
        priority_weight=priority_weight,
    )

    db.add(plan)
    db.commit()

    return {"message": "Subscription plan created"}