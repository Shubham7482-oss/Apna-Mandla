# app/models/product_stock_ledger.py

from datetime import datetime
from sqlalchemy import ForeignKey, String, Integer, DateTime, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ProductStockLedger(Base):
    """
    Product Stock Ledger

    Tracks stock movement:
    - ADD
    - SALE
    - REFUND
    - ADJUSTMENT
    """

    __tablename__ = "product_stock_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # 🔗 Product reference
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 📦 Stock change amount
    quantity_change: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 🔄 Type of change
    change_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    # ADD | SALE | REFUND | ADJUSTMENT

    # 🧾 Optional reference (order_id / admin_action_id etc.)
    reference_id: Mapped[int | None] = mapped_column(
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    # Relationship
    product = relationship("Product")

    __table_args__ = (
        CheckConstraint(
            "change_type IN ('ADD','SALE','REFUND','ADJUSTMENT')",
            name="ck_stock_change_type_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ProductStockLedger product_id={self.product_id} "
            f"change_type={self.change_type} "
            f"quantity_change={self.quantity_change}>"
        )