from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from decimal import Decimal

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.rbac import require_roles, require_plan_admin
from app.models.user import User
from app.models.shop_profile import ShopProfile
from app.models.subscription_plan import SubscriptionPlan
from app.services.subscription_service import SubscriptionService
from app.services.admin_audit_service import log_admin_action
from app.utils.response import standard_response
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/subscription", tags=["Subscription"])


# ───────────────────────────────
# 1. PURCHASE SUBSCRIPTION
# ───────────────────────────────
@router.post("/purchase", response_model=None)
def purchase_subscription(
    plan_id: int,
    duration_days: int = 30,
    current_user: User = Depends(require_roles(["shop"])),
    db: Session = Depends(get_db),
    request: Request = None,
):
    result = SubscriptionService.purchase_subscription(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
        duration_days=duration_days,
    )

    ip = request.client.host if request and request.client else None

    log_admin_action(
        db=db,
        admin_id=None,
        module="subscription",
        action=f"PURCHASE_PLAN:{plan_id}",
        target_id=str(current_user.id),
        ip_address=ip,
    )

    payload = {
        "plan": result["plan_name"],
        "expiry_date": result["expiry"],
        "remaining_balance": result["balance"],
    }

    return standard_response(
        data=payload,
        message="Subscription activated successfully",
    )


# ───────────────────────────────
# 2. DASHBOARD SUMMARY
# ───────────────────────────────
@router.get("/dashboard-summary", response_model=None)
def get_subscription_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = db.query(ShopProfile).filter(
        ShopProfile.user_id == current_user.id
    ).first()

    if not shop:
        raise HTTPException(status_code=404, detail="Shop profile not found")

    active_sub = SubscriptionService.get_active_subscription(db, shop.id)
    plan = SubscriptionService.get_plan_limits(db, shop.id)

    from app.models.product import Product
    from app.models.discount import DiscountRule

    product_count = db.query(Product).filter(
        Product.shop_id == shop.id
    ).count()

    discount_count = db.query(DiscountRule).filter(
        DiscountRule.shop_id == shop.id
    ).count()

    if not active_sub or not plan:
        return standard_response(
            data={
                "has_active_plan": False,
                "current_usage": {
                    "products": product_count,
                    "discounts": discount_count,
                },
            },
            message="No active subscription. Please purchase a plan.",
        )

    return standard_response(
        data={
            "has_active_plan": True,
            "plan_name": plan.name,
            "expiry_date": active_sub.end_date,
            "days_remaining": (active_sub.end_date - datetime.utcnow()).days,
            "limits": {
                "max_products": plan.max_products,
                "current_products": product_count,
                "available_products": max(0, plan.max_products - product_count),
                "max_discounts": plan.max_discounts,
                "current_discounts": discount_count,
                "available_discounts": max(0, plan.max_discounts - discount_count),
            },
        },
        message="Subscription summary fetched successfully",
    )


# ───────────────────────────────
# 👑 PLAN_ADMIN: MANAGE PLANS
# ───────────────────────────────
@router.get("/plans/all")
def get_all_plans_admin(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_plan_admin)
):
    """PLAN_ADMIN: List all available plans."""
    return db.query(SubscriptionPlan).all()

@router.patch("/plans/{plan_id}")
def update_plan(
    plan_id: int,
    price: Optional[float] = Body(None),
    max_products: Optional[int] = Body(None),
    max_discounts: Optional[int] = Body(None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_plan_admin)
):
    """PLAN_ADMIN: Update subscription plan details."""
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    if price is not None: plan.price = Decimal(str(price))
    if max_products is not None: plan.max_products = max_products
    if max_discounts is not None: plan.max_discounts = max_discounts
    
    db.commit()
    return SuccessResponse(success=True, message="Plan updated successfully")
