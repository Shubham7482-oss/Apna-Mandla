# app/models/shop_category.py

from sqlalchemy import String, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ShopCategory(Base):
    __tablename__ = "shop_categories"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    image_url = Column(String(255), nullable=True) # New field for category image

    template_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # ───────────────────────────────
    # RELATIONSHIPS
    # ───────────────────────────────
    shops: Mapped[list["Shop"]] = relationship(
        "Shop",
        back_populates="category",
        cascade="all",
    )

    plans: Mapped[list["SubscriptionPlan"]] = relationship(
        "SubscriptionPlan",
        back_populates="category",
    )