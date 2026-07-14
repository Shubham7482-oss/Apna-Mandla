from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.models.user import User
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.wallet import Wallet
from app.models.ledger_entry import LedgerEntry

class SubscriptionService:

    # ─────────────────────────────────────────────────────────
    # 1. PURCHASE LOGIC (WITH WALLET & LEDGER)
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def purchase_subscription(db: Session, user_id: int, plan_id: int, duration_days: int):
        """Purchase subscription with wallet balance using the new user_id based Wallet model."""
        try:
            # 1. Basic checks
            user = db.query(User).filter(User.id == user_id).first()
            plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
            if not user or not plan:
                raise HTTPException(status_code=404, detail="User or Plan not found")

            # 2. Fetch Wallet (Universal user_id link)
            wallet = db.query(Wallet).filter(Wallet.user_id == user_id).with_for_update().first()
            if not wallet or wallet.balance < plan.price:
                raise HTTPException(status_code=400, detail="Insufficient wallet balance")

            # 3. Deduct & Log
            wallet.balance -= plan.price
            db.add(LedgerEntry(
                wallet_id=wallet.id, 
                entry_type="DEBIT", 
                amount=plan.price, 
                description=f"Sub Purchase: {plan.name}"
            ))

            # 4. Create or Extend Subscription
            now = datetime.utcnow()
            
            # Check for existing active subscription
            existing_sub = db.query(Subscription).filter(
                Subscription.user_id == user_id, 
                Subscription.status == "ACTIVE"
            ).with_for_update().first()

            if existing_sub:
                if existing_sub.end_date < now:
                    existing_sub.start_date = now
                    existing_sub.end_date = now + timedelta(days=duration_days)
                else:
                    existing_sub.end_date += timedelta(days=duration_days)
                existing_sub.plan_id = plan.id
                result_sub = existing_sub
            else:
                new_sub = Subscription(
                    user_id=user_id,
                    plan_id=plan.id,
                    start_date=now,
                    end_date=now + timedelta(days=duration_days),
                    status="ACTIVE"
                )
                db.add(new_sub)
                result_sub = new_sub
            
            db.commit()
            return {"plan_name": plan.name, "expiry": result_sub.end_date, "balance": float(wallet.balance)}

        except Exception as e:
            db.rollback()
            if isinstance(e, HTTPException):
                raise e
            print(f"Transaction Error: {e}")
            raise HTTPException(status_code=500, detail="Subscription transaction failed")

    # ─────────────────────────────────────────────────────────
    # 2. VALIDATION & LIMIT LOGIC (OLD REFINED)
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def get_active_subscription(db: Session, user_id: int):
        """Check if user has a valid active subscription"""
        return (
            db.query(Subscription)
            .filter(
                Subscription.user_id == user_id,
                Subscription.status == "ACTIVE",
                Subscription.end_date > datetime.utcnow(),
            )
            .first()
        )

    @staticmethod
    def get_plan_limits(db: Session, user_id: int):
        """Get the details of the currently active plan"""
        sub = SubscriptionService.get_active_subscription(db, user_id)
        if not sub:
            return None
        return db.query(SubscriptionPlan).filter(SubscriptionPlan.id == sub.plan_id).first()

    @staticmethod
    def can_add_product(db: Session, user_id: int, current_product_count: int):
        """Verify if the user can add more products based on their plan"""
        plan = SubscriptionService.get_plan_limits(db, user_id)
        if not plan:
            return False
        return current_product_count < plan.max_products

    @staticmethod
    def can_add_discount(db: Session, user_id: int, current_discount_count: int):
        """Verify if the user can create more discount coupons"""
        plan = SubscriptionService.get_plan_limits(db, user_id)
        if not plan:
            return False
        return current_discount_count < plan.max_discounts