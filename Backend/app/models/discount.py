from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin

class DiscountRule(Base, TimestampMixin):
    """
    Gold Feature: Advanced Discount Rules for Shops
    """
    __tablename__ = "discount_rules"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shop_profiles.id"), nullable=False)
    
    title = Column(String(100), nullable=False) # e.g., "Mega Holi Sale"
    rule_type = Column(String(30), nullable=False) # QUANTITY / FIRST_ORDERS / PRODUCT / DELIVERY
    
    # Logic Parameters
    min_order_value = Column(Float, default=0.0)
    min_quantity = Column(Integer, default=0)
    max_uses = Column(Integer, default=0) # For "First 50 orders"
    current_uses = Column(Integer, default=0)
    
    # Discount value
    discount_percent = Column(Float, default=0.0)
    max_discount_amount = Column(Float, nullable=True) # Cap for percentage
    flat_amount = Column(Float, default=0.0) # Rs. 50 off
    
    # Product specific
    target_product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    
    is_active = Column(Boolean, default=True)
    expiry_date = Column(DateTime, nullable=True)

    shop = relationship("ShopProfile", back_populates="discount_rules")
