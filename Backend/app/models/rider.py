from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, 
    DateTime, UniqueConstraint, Text
)
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin, SoftArchiveMixin

class Rider(Base, TimestampMixin, SoftArchiveMixin):
    __tablename__ = "riders"

    id = Column(Integer, primary_key=True, index=True)

    # ========================
    # BASIC LINKS
    # ========================
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    rider_profile_id = Column(
        Integer,
        ForeignKey("rider_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    work_id = Column(String(50), nullable=False, unique=True, index=True)
    qr_code_url = Column(String(255), nullable=True)

    # ========================
    # ADMIN APPROVAL LIFECYCLE (NEW)
    # ========================
    approval_status = Column(
        String(20), 
        default="PENDING", 
        nullable=False, 
        index=True
    ) # PENDING, APPROVED, REJECTED

    # Jab Admin reject karega toh wajah yahan save hogi
    rejection_reason = Column(Text, nullable=True)

    # ========================
    # DUTY & STATUS
    # ========================
    on_duty = Column(Boolean, default=False, nullable=False)

    current_order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    duty_started_at = Column(DateTime, nullable=True)
    last_duty_ended_at = Column(DateTime, nullable=True)

    # ========================
    # VERIFICATION & CONTROL
    # ========================
    police_verified = Column(Boolean, default=False, nullable=False)
    kyc_verified = Column(Boolean, default=False, nullable=False)

    blacklisted = Column(Boolean, default=False, nullable=False)
    blacklist_reason = Column(String(255), nullable=True)

    # ========================
    # COD ENGINE
    # ========================
    cod_liability = Column(Integer, default=0, nullable=False)
    is_cod_blocked = Column(Boolean, default=False, nullable=False)

    # ========================
    # PROBATION & RISK
    # ========================
    is_on_probation = Column(Boolean, default=True, nullable=False)
    completed_orders_count = Column(Integer, default=0, nullable=False)
    risk_score = Column(Integer, default=100, nullable=False)
    last_cod_settlement_at = Column(DateTime, nullable=True)

    # ========================
    # RELATIONSHIPS
    # ========================
    user = relationship("User", foreign_keys=[user_id])
    profile = relationship("RiderProfile", foreign_keys=[rider_profile_id])

    current_order = relationship(
        "Order",
        foreign_keys=[current_order_id],
        post_update=True,
    )

    # ========================
    # CONSTRAINTS
    # ========================
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_rider_user"),
        UniqueConstraint("work_id", name="uq_rider_work_id"),
    )