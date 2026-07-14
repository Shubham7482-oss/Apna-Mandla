from sqlalchemy import (
    Integer, String, ForeignKey, 
    DateTime, Enum, Numeric
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
import enum
from typing import List, Optional

from app.models.base import Base, TimestampMixin, SoftArchiveMixin

# ===============================
# ENUMS
# ===============================

class OrderStatus(str, enum.Enum):
    PAYMENT_PENDING = "PAYMENT_PENDING"
    CREATED = "CREATED"
    SHOP_ACCEPTED = "SHOP_ACCEPTED"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    BROADCASTING = "BROADCASTING" 
    RIDER_ASSIGNED = "RIDER_ASSIGNED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"

class PaymentMode(str, enum.Enum):
    PREPAID = "PREPAID"
    COD = "COD"
    UDHAR = "UDHAR"

class OrderType(str, enum.Enum):
    DIRECT_SHOP = "DIRECT_SHOP"
    OPEN_MARKET = "OPEN_MARKET"

# ===============================
# ORDER MODEL (MODERNIZED)
# ===============================

class Order(Base, TimestampMixin, SoftArchiveMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Core Links
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    shop_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("shops.id", ondelete="RESTRICT"), nullable=True, index=True)
    mandla_id: Mapped[int] = mapped_column(Integer, ForeignKey("mandlas.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Hybrid Order Logic
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType), default=OrderType.DIRECT_SHOP, nullable=False)

    # Order Data, Pricing & Proofs
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0.00)
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0.00)
    applied_discount_rule_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("discount_rules.id"), nullable=True)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0.00)
    delivery_fee: Mapped[float] = mapped_column(Numeric(10, 2), default=0.00)
    delivery_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.CREATED, nullable=False, index=True)
    payment_mode: Mapped[PaymentMode] = mapped_column(Enum(PaymentMode), nullable=False, default=PaymentMode.PREPAID)

    # Verification & Proofs
    delivery_otp: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)
    pickup_photo: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    delivery_photo: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Rider Assignment
    assigned_rider_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("rider_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    broadcast_deadline: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    broadcast_radius: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    transfer_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    customer: Mapped["User"] = relationship("User", foreign_keys=[customer_id])
    shop: Mapped[Optional["Shop"]] = relationship("Shop", foreign_keys=[shop_id])
    assigned_rider: Mapped[Optional["RiderProfile"]] = relationship("RiderProfile", foreign_keys=[assigned_rider_id])
    items: Mapped[List["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="order", cascade="all, delete-orphan")
    parcel: Mapped[Optional["Parcel"]] = relationship("Parcel", uselist=False)
