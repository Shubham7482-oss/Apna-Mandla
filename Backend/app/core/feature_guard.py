from datetime import datetime
from typing import Optional
from app.models.subscription import Subscription
from app.models.shop import Shop

def get_active_subscription(shop: Shop) -> Optional[Subscription]:
    """
    Generic function to get active subscription for a shop.
    """
    if not shop.subscriptions:
        return None

    now = datetime.utcnow()
    for sub in shop.subscriptions:
        if (
            sub.status == "ACTIVE"
            and sub.start_date <= now
            and sub.end_date >= now
        ):
            return sub
    return None

def is_premium(shop: Shop) -> bool:
    """
    Checks if the shop has a premium subscription (any plan other than NONE or BASIC).
    """
    sub = get_active_subscription(shop)
    if not sub:
        return False
    
    # Any plan that isn't the free/basic tier is considered premium.
    return sub.plan.name.upper() not in ["NONE", "BASIC"]

def check_feature_access(shop: Shop, required_plan: str = "BASIC") -> bool:
    """
    Checks if the shop has access to a feature based on their plan.
    required_plan priority: GOLD > SILVER > BASIC > NONE
    """
    sub = get_active_subscription(shop)
    if not sub:
        return required_plan == "NONE"
    
    plan_priority = {"GOLD": 3, "SILVER": 2, "BASIC": 1, "NONE": 0}
    user_plan = sub.plan.name.upper()
    
    return plan_priority.get(user_plan, 0) >= plan_priority.get(required_plan.upper(), 0)