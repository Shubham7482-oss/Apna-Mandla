# app/services/shop_engine.py

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models.shop import Shop
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.rating import Rating  # ✅ ShopRating ki jagah ab Rating import hoga
from app.models.ad import Ad


class ShopEngine:

    # ───────────────────────────────
    # ACTIVE SUBSCRIPTION
    # ───────────────────────────────
    @staticmethod
    def get_active_subscription(db: Session, shop_id: int):
        return (
            db.query(Subscription)
            .filter(
                Subscription.shop_id == shop_id,
                Subscription.status == "ACTIVE",
                Subscription.end_date > datetime.now(timezone.utc), # ✅ Fixed utcnow warning
            )
            .first()
        )

    # ───────────────────────────────
    # FEATURE LIMITS
    # ───────────────────────────────
    @staticmethod
    def get_plan(db: Session, shop_id: int):
        sub = ShopEngine.get_active_subscription(db, shop_id)
        if not sub:
            return None
        return db.query(SubscriptionPlan).filter(
            SubscriptionPlan.id == sub.plan_id
        ).first()

    # ───────────────────────────────
    # WEBSITE TIER
    # ───────────────────────────────
    @staticmethod
    def get_website_tier(db: Session, shop_id: int):
        plan = ShopEngine.get_plan(db, shop_id)
        if not plan:
            return "FREE"

        if plan.price >= 999:
            return "ELITE"
        elif plan.price >= 399:
            return "PRO"
        return "BASIC"

    # ───────────────────────────────
    # RATING SUMMARY (Updated for Generic Rating)
    # ───────────────────────────────
    @staticmethod
    def get_rating_summary(db: Session, shop_id: int):
        # Filter by target_id (shop_id) and target_type ("shop")
        query = db.query(Rating).filter(
            Rating.target_id == shop_id,
            Rating.target_type == "shop"
        )
        
        total = query.count()

        if total == 0:
            return 0, 0

        avg = db.query(func.avg(Rating.rating)).filter(
            Rating.target_id == shop_id,
            Rating.target_type == "shop"
        ).scalar()

        return round(float(avg), 2), total

    # ───────────────────────────────
    # TOP RATED SHOPS
    # ───────────────────────────────
    @staticmethod
    def get_top_rated_shops(db: Session, min_rating=4.5):
        return (
            db.query(Shop)
            .join(Rating, (Rating.target_id == Shop.id) & (Rating.target_type == "shop"))
            .group_by(Shop.id)
            .having(func.avg(Rating.rating) >= min_rating)
            .order_by(desc(func.avg(Rating.rating)))
            .all()
        )

    # ───────────────────────────────
    # AD PRIORITY BOOST
    # ───────────────────────────────
    @staticmethod
    def get_active_ads(db: Session):
        return (
            db.query(Ad)
            .filter(
                Ad.is_active == True,
                Ad.start_date <= datetime.now(timezone.utc),
            )
            .order_by(desc(Ad.priority))
            .all()
        )

    # ───────────────────────────────
    # MARKETPLACE RANKING SCORE
    # ───────────────────────────────
    @staticmethod
    def calculate_shop_score(db: Session, shop: Shop):

        rating_avg, rating_count = ShopEngine.get_rating_summary(db, shop.id)

        plan = ShopEngine.get_plan(db, shop.id)
        priority_weight = plan.priority_weight if plan else 1

        # Score calculation logic
        score = (rating_avg * 10) + (rating_count * 0.5) + (priority_weight * 5)

        return score