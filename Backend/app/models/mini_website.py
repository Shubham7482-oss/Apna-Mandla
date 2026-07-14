# app/models/mini_website.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, SoftArchiveMixin


class MiniWebsite(Base, TimestampMixin, SoftArchiveMixin):
    """
    Universal Digital Mini Website for Apna Mandla.

    This represents:
    - individual person
    - worker / rider / helper
    - shop / business
    - institution / govt unit

    RULES:
    - Exactly ONE mini website per user/entity
    - Public-facing but controlled
    - Archive-only, never delete
    """

    __tablename__ = "mini_websites"

    id = Column(Integer, primary_key=True, index=True)

    # ───────────────────────────────
    # OWNER LINK
    # ───────────────────────────────
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    # ───────────────────────────────
    # PUBLIC IDENTITY
    # ───────────────────────────────
    display_name = Column(String(150), nullable=False)
    slug = Column(String(180), nullable=False, unique=True)
    short_bio = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    # ───────────────────────────────
    # VISUALS
    # ───────────────────────────────
    profile_photo_url = Column(String(255), nullable=True)
    cover_photo_url = Column(String(255), nullable=True)
    logo_url = Column(String(255), nullable=True)

    # ───────────────────────────────
    # MULTIMEDIA (SUBSCRIPTION BASED)
    # ───────────────────────────────
    # For Gold users: Multiple slideable banners
    banner_images_json = Column(Text, nullable=True) # Stores list of URLs: ["url1", "url2"]
    
    # For Silver/Gold users: Smaller gallery images
    gallery_images_json = Column(Text, nullable=True) # Stores list of URLs: ["img1", "img2"]

    # ───────────────────────────────
    # STATUS & AVAILABILITY
    # ───────────────────────────────
    is_open = Column(Boolean, default=False, nullable=False)
    availability_status = Column(
        String(30),
        default="CLOSED",  # AVAILABLE / BUSY / CLOSED
        nullable=False,
    )

    # ───────────────────────────────
    # SOCIAL & LINKS (GOLD FEATURE)
    # ───────────────────────────────
    facebook_url = Column(String(255), nullable=True)
    instagram_url = Column(String(255), nullable=True)
    twitter_url = Column(String(255), nullable=True)
    youtube_url = Column(String(255), nullable=True)

    # ───────────────────────────────
    # CUSTOMIZATION
    # ───────────────────────────────
    theme_color = Column(String(7), default="#0d6efd", nullable=False) # Hex Code

    # ───────────────────────────────
    # TRUST & VERIFICATION
    # ───────────────────────────────
    documents_verified = Column(Boolean, default=False, nullable=False)
    verified_badge = Column(Boolean, default=False, nullable=False)

    # ───────────────────────────────
    # SYSTEM CONTROLS
    # ───────────────────────────────
    public_visible = Column(Boolean, default=True, nullable=False)
    suspended = Column(Boolean, default=False, nullable=False)
    suspension_reason = Column(String(255), nullable=True)

    # ───────────────────────────────
    # RELATIONSHIPS
    # ───────────────────────────────
    user = relationship("User", back_populates="mini_website")

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_mini_website_user"),
    )