from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.discount import DiscountRule
from app.models.order import Order
from app.core.feature_guard import check_feature_access
from app.models.user import User
from app.models.shop import Shop
import json

class DiscountEngine:
    @staticmethod
    def calculate_order_discount(db: Session, shop_user: User, items: list, subtotal: float):
        """
        Calculates total discount for an order based on shop rules.
        items: list of dicts {'product_id': id, 'quantity': q, 'price': p}
        """
        shop = db.query(Shop).filter(Shop.user_id == shop_user.id).first()
        if not shop:
            return 0.0
        
        # 1. Gold Check: If shop is not GOLD, no discounts applied
        if not check_feature_access(shop, "GOLD"):
            return 0.0

        shop_profile = shop_user.shop_profile
        if not shop_profile:
            return 0.0

        # 2. Fetch active rules
        rules = db.query(DiscountRule).filter(
            DiscountRule.shop_id == shop_profile.id,
            DiscountRule.is_active == True
        ).all()

        total_discount = 0.0
        total_quantity = sum(item['quantity'] for item in items)

        for rule in rules:
            rule_discount = 0.0
            
            # Rule: FIRST_ORDERS (e.g., First 50 customers)
            if rule.rule_type == "FIRST_ORDERS":
                if rule.current_uses < rule.max_uses:
                    rule_discount = rule.flat_amount or (subtotal * (rule.discount_percent / 100))

            # Rule: QUANTITY (e.g., Buy 5+ items)
            elif rule.rule_type == "QUANTITY":
                if total_quantity >= rule.min_quantity:
                    rule_discount = rule.flat_amount or (subtotal * (rule.discount_percent / 100))

            # Rule: PRODUCT (Specific item discount)
            elif rule.rule_type == "PRODUCT":
                for item in items:
                    if item['product_id'] == rule.target_product_id:
                        item_total = item['quantity'] * item['price']
                        rule_discount += item_total * (rule.discount_percent / 100)

            # Cap the discount if rule has max_discount_amount
            if rule.max_discount_amount and rule_discount > rule.max_discount_amount:
                rule_discount = rule.max_discount_amount
            
            # Apply the best rule (or we can sum them depending on business logic)
            # For now, we take the maximum possible discount among all applicable rules
            total_discount = max(total_discount, rule_discount)

        return round(total_discount, 2)
