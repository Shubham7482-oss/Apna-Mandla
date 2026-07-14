from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Enum
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin
import enum

class AdType(str, enum.Enum):
    BANNER = "BANNER"

class Ad(Base, TimestampMixin):
    __tablename__ = "ads"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    mandla_id = Column(Integer, ForeignKey("mandlas.id"), nullable=False) # Area-based filtering
    
    image_url = Column(String(255), nullable=False)
    ad_type = Column(String(20), default="BANNER")
    
    # Subscription periods
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    
    is_active = Column(Boolean, default=True)
    click_count = Column(Integer, default=0)

    shop = relationship("Shop")
    mandla = relationship("Mandla")
