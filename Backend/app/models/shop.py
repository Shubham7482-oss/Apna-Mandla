from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, 
    DateTime, UniqueConstraint, Text
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.models.base import Base, TimestampMixin, SoftArchiveMixin
from app.models.shop_category import ShopCategory

class Shop(Base, TimestampMixin, SoftArchiveMixin):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, index=True)
    image_url = Column(String(255), nullable=True)

    # ───────────────────────────────
    # PUBLIC WEBSITE & IDENTITY
    # ───────────────────────────────
    slug = Column(
        String(150),
        unique=True,
        nullable=False,
        index=True,
    )

    # 💎 SUBSCRIPTION & QR LOGIC (Monetization Feature)
    is_subscribed = Column(Boolean, default=False, nullable=False)
    
    # Pro Shops apna naam khud likh payengi
    custom_display_name = Column(String(100), nullable=True) 
    
    # Free Shops ko ye random ID dikhegi (e.g. MANDLA-P-8823)
    random_id_name = Column(String(50), unique=True, nullable=False)

    # ───────────────────────────────
    # LINKED ENTITIES
    # ───────────────────────────────
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    shop_profile_id = Column(
        Integer,
        ForeignKey("shop_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    category_id = Column(
        Integer,
        ForeignKey("shop_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ───────────────────────────────
    # ADMIN APPROVAL & STATUS
    # ───────────────────────────────
    approval_status = Column(
        String(20),
        nullable=False,
        default="PENDING", # PENDING, APPROVED, REJECTED
        index=True,
    )

    rejection_reason = Column(Text, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ───────────────────────────────
    # LIVE OPERATION STATUS
    # ───────────────────────────────
    is_open = Column(Boolean, default=False, nullable=False)
    availability_status = Column(String(30), default="CLOSED", nullable=False)
    last_opened_at = Column(DateTime(timezone=True), nullable=True)
    last_closed_at = Column(DateTime(timezone=True), nullable=True)

    # ───────────────────────────────
    # SYSTEM FLAGS
    # ───────────────────────────────
    public_visible = Column(Boolean, default=False, nullable=False)
    suspended = Column(Boolean, default=False, nullable=False)
    suspension_reason = Column(String(255), nullable=True)

    # ───────────────────────────────
    # RELATIONSHIPS
    # ───────────────────────────────
    owner = relationship("User", foreign_keys=[user_id], backref="owned_shop")
    approver = relationship("User", foreign_keys=[approved_by_id])
    
    profile = relationship("ShopProfile")
    category = relationship("ShopCategory", back_populates="shops")
    udhar_accounts = relationship("UdharAccount", back_populates="lender_shop", foreign_keys="UdharAccount.lender_shop_id")
    
    # Order items tracking (QR scanning ke liye)
    order_items = relationship("OrderItem", back_populates="shop")

    # Products belonging to this shop
    products = relationship(
        "Product",
        back_populates="shop",
        cascade="all, delete-orphan",
    )
    
    # Subscription tracking (Payment/Expiry ke liye)
    # Back-populated by Subscription.shop
    subscriptions = relationship("Subscription", back_populates="shop")

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_shop_user"),
    )

# 💡 Helper function to generate Random ID (MANDLA-P-XXXX)
# Ise aap shop create karte waqt backend logic mein use kar sakte hain

def generate_shop_random_id():
    return f"MANDLA-P-{uuid.uuid4().hex[:6].upper()}"