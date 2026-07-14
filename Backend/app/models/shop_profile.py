from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin

class ShopProfile(Base, TimestampMixin):
    __tablename__ = "shop_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    mandla_id = Column(Integer, ForeignKey("mandlas.id"), nullable=False)

    business_name = Column(String(150), nullable=False)
    category = Column(String(100), nullable=False)
    address = Column(Text, nullable=True)
    plus_code = Column(String(100), nullable=True) # Replaced lat/long with plus_code
    
    # Status
    approval_status = Column(String(20), default="PENDING") # PENDING, APPROVED, REJECTED
    rejection_reason = Column(Text, nullable=True)
    
    # Branding
    logo_url = Column(String(255), nullable=True)
    banner_url = Column(String(255), nullable=True)
    
    # KYC
    aadhar_url = Column(String(255), nullable=True)
    pan_url = Column(String(255), nullable=True)
    shop_images_json = Column(Text, nullable=True)
    
    # Finance
    bank_details_json = Column(Text, nullable=True)

    user = relationship("User", back_populates="shop_profile")
    mandla = relationship("Mandla", back_populates="shops")
    discount_rules = relationship("DiscountRule", back_populates="shop")
