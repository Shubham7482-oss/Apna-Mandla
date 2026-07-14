from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Date,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, SoftArchiveMixin


class CustomerProfile(Base, TimestampMixin, SoftArchiveMixin):
    """
    Customer profile for Apna Mandla.

    Notes:
    - Customers may exist without full Aadhaar verification
    - Risk-based Aadhaar applies later (behavioural / threshold based)
    - Profile is NEVER deleted, only archived
    """

    __tablename__ = "customer_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # ───────────────────────────────
    # LINKED USER (AUTH TABLE LATER)
    # ───────────────────────────────
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    # ───────────────────────────────
    # BASIC IDENTITY
    # ───────────────────────────────
    full_name = Column(String(150), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)

    # ───────────────────────────────
    # CONTACT (VERIFIED FLAGS)
    # ───────────────────────────────
    phone_verified = Column(Boolean, default=False, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)

    # ───────────────────────────────
    # ✅ NEW: LOCATION UPGRADE (System 1)
    # ───────────────────────────────
    # Pinpoint Plus Code for customer's primary address
    default_plus_code = Column(String(50), nullable=True, index=True)
    
    # Area name or Landmark for easier identification
    area_name = Column(String(100), nullable=True)

    # ───────────────────────────────
    # RISK & TRUST
    # ───────────────────────────────
    aadhaar_required = Column(Boolean, default=False, nullable=False)
    aadhaar_verified = Column(Boolean, default=False, nullable=False)
    trust_score = Column(Integer, default=0, nullable=False)

    # ───────────────────────────────
    # SYSTEM FLAGS
    # ───────────────────────────────
    blacklisted = Column(Boolean, default=False, nullable=False)
    blacklist_reason = Column(String(255), nullable=True)

    # ───────────────────────────────
    # RELATIONSHIPS (DECLARED LATE)
    # ───────────────────────────────
    user = relationship("User", back_populates="customer_profile")

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_customer_profile_user"),
    )