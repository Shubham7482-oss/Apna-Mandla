# backend/app/models/parcel.py
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Enum as SQLAlchemyEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.models.base import Base
import datetime
from typing import Optional
import enum

class ParcelStatus(str, enum.Enum):
    PENDING = "pending"
    SEARCHING_FOR_RIDER = "searching_for_rider"
    ASSIGNED = "assigned"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class PaymentMode(str, enum.Enum):
    CASH_ON_DELIVERY = "cash_on_delivery"
    PREPAID = "prepaid"

class Parcel(Base):
    __tablename__ = 'parcels'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey('orders.id'), nullable=False, unique=True)
    tracking_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    
    # Location Info
    pickup_plus_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    dropoff_plus_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    status: Mapped[ParcelStatus] = mapped_column(SQLAlchemyEnum(ParcelStatus), nullable=False, default=ParcelStatus.PENDING)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    length: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    width: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    height: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    order: Mapped["Order"] = relationship("Order")
    sender: Mapped["User"] = relationship("User")
