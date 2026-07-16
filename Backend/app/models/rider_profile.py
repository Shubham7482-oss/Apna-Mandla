from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    DateTime,
    Enum,
    func,
    Text,
    Float # Ratings aur performance ke liye
)
from sqlalchemy.orm import relationship
import enum
from datetime import datetime

from app.models.base import Base, TimestampMixin, SoftArchiveMixin

class RiderStatus(str, enum.Enum): 
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RiderProfile(Base, TimestampMixin, SoftArchiveMixin):
    __tablename__ = "rider_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # ───────────────────────────────
    # LINKED USER
    # ───────────────────────────────
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    mandla_id = Column(
        Integer,
        ForeignKey("mandlas.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # ───────────────────────────────
    # VEHICLE & DOCUMENTS
    # ───────────────────────────────
    vehicle_type = Column(String(50), nullable=False) 
    license_number = Column(String(100), nullable=True)

    # ───────────────────────────────
    # TIERED VERIFICATION
    # ───────────────────────────────
    verification_tier = Column(String(20), default="NORMAL") # NORMAL (Prepaid) / FULL (COD + High Risk)
    
    # Document URLs
    aadhar_url = Column(String(255), nullable=True)
    license_url = Column(String(255), nullable=True)
    vehicle_photo_url = Column(String(255), nullable=True)
    police_verification_url = Column(String(255), nullable=True) # Required for FULL tier
    
    # Bank for Payouts
    bank_details_json = Column(Text, nullable=True)

    # ───────────────────────────────
    # ✅ AUTOMATION UPGRADE (System 2)
    # ───────────────────────────────
    is_online = Column(Boolean, default=False, nullable=False)
    current_plus_code = Column(String(50), nullable=True, index=True)
    
    # Isse system ko pata chalega ki rider ka location data fresh hai ya nahi
    last_location_update = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Performance metrics for auto-assignment priority
    rating = Column(Float, default=5.0)
    total_deliveries = Column(Integer, default=0)

    # ───────────────────────────────
    # APPROVAL STATUS
    # ───────────────────────────────
    status = Column(
        Enum(RiderStatus, name="rider_status_enum"),
        nullable=False,
        default=RiderStatus.PENDING,
    )

    rejection_reason = Column(Text, nullable=True)
    is_active = Column(Boolean, default=False)

    # Relationships
    user = relationship("User", back_populates="rider_profile")
    mandla = relationship("Mandla")

    orders = relationship(
        "Order",
        foreign_keys="Order.assigned_rider_id",
        back_populates="assigned_rider",
    )