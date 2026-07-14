from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.base import Base, TimestampMixin, SoftArchiveMixin

class OrderItem(Base, TimestampMixin, SoftArchiveMixin):
    """
    Advanced OrderItem model for Apna Mandla.
    Supports Multi-shop pickup and QR verification.
    """

    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)

    # ───────────────────────────────
    # LINKS
    # ───────────────────────────────
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Kis dukan se ye item pick hua (QR Scan ke baad update hoga)
    shop_id = Column(
        Integer,
        ForeignKey("shops.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ───────────────────────────────
    # ITEM SNAPSHOT
    # ───────────────────────────────
    product_name = Column(String(180), nullable=False)
    quantity = Column(Integer, nullable=False)
    price_per_unit = Column(Integer, nullable=False)
    total_price = Column(Integer, nullable=False)

    # ───────────────────────────────
    # LOGISTICS & QR TRACKING
    # ───────────────────────────────
    # Status: PENDING, PICKED, OUT_OF_STOCK
    pickup_status = Column(String(30), default="PENDING")
    
    # Shopkeeper ki confirmation (Scan ke baad dukanwala 'OK' karega)
    is_shop_confirmed = Column(Boolean, default=False)
    
    picked_at = Column(DateTime, nullable=True)

    # ───────────────────────────────
    # RELATIONSHIPS
    # ───────────────────────────────
    order = relationship("Order", back_populates="items")
    shop = relationship("Shop") # Item level par shop tracking


# 👇 IMPORTANT: explicit export
__all__ = ["OrderItem"]