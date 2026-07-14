from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.core.database import get_db
from app.core.rbac import require_business_user
from app.core.feature_guard import check_feature_access
from app.models.discount import DiscountRule
from app.models.user import User
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/discounts", tags=["Discounts & Offers"])

@router.post("/create")
def create_discount_rule(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_business_user)
):
    # 🔥 MANDATORY GOLD CHECK
    if not check_feature_access(current_user, "GOLD"):
        raise HTTPException(status_code=403, detail="Advanced Offers & Discounts are only available for GOLD subscribers.")

    # Shop lookup
    shop = current_user.shop_profile
    if not shop:
        raise HTTPException(status_code=404, detail="Shop profile not found")

    new_rule = DiscountRule(
        shop_id=shop.id,
        title=payload.get("title"),
        rule_type=payload.get("rule_type"),
        min_order_value=payload.get("min_order_value", 0),
        min_quantity=payload.get("min_quantity", 0),
        max_uses=payload.get("max_uses", 0),
        discount_percent=payload.get("discount_percent", 0),
        flat_amount=payload.get("flat_amount", 0),
        target_product_id=payload.get("target_product_id"),
        is_active=True
    )

    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)

    return SuccessResponse(success=True, data={"id": new_rule.id}, message="Discount offer created successfully!")

@router.get("/my-offers")
def get_my_discounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_business_user)
):
    # Even listing might be restricted or just show empty if not Gold
    if not check_feature_access(current_user, "GOLD"):
        return SuccessResponse(success=True, data=[], message="Upgrade to GOLD to use offers.")

    shop = current_user.shop_profile
    rules = db.query(DiscountRule).filter(DiscountRule.shop_id == shop.id, DiscountRule.is_active == True).all()
    
    return SuccessResponse(success=True, data=rules, message="Offers fetched")
