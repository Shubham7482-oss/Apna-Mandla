from sqlalchemy import Integer, ForeignKey, CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

class Rating(Base):
    __tablename__ = "ratings"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Kis Order ke liye rating ho rahi hai
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
    )

    # Jo rate kar raha hai (Rider ya Customer)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Jise rate kiya ja raha hai (Shop ID, Rider ID, ya Customer ID)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Kaunsa entity hai: 'SHOP', 'RIDER', 'CUSTOMER'
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(String(255), nullable=True)

    # ⭐ Constraints
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="rating_range_check"),
        # Unique constraint: Ek order ke liye ek user ek hi target_type ko rate kar sakta hai
        # Matlab: Customer ek order par 1 Shop rating aur 1 Rider rating de sakta hai.
        UniqueConstraint('order_id', 'user_id', 'target_type', name='unique_order_rating_per_type'),
    )

    # Relationships
    order: Mapped["Order"] = relationship()
    user: Mapped["User"] = relationship()