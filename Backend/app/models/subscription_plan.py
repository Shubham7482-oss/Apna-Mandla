# app/models/subscription_plan.py

from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(primary_key=True)

    category_id: Mapped[int] = mapped_column(
        ForeignKey("shop_categories.id"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    price: Mapped[int] = mapped_column(Integer, nullable=False)

    max_products: Mapped[int] = mapped_column(Integer, default=10)
    max_discounts: Mapped[int] = mapped_column(Integer, default=0)

    priority_weight: Mapped[int] = mapped_column(Integer, default=1)

    # Relationships
    category: Mapped["ShopCategory"] = relationship(back_populates="plans")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="plan")