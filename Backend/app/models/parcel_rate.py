# backend/app/models/parcel_rate.py
from sqlalchemy import Column, Integer, String, Float, DateTime
from app.models.base import Base
import datetime

class ParcelRate(Base):
    __tablename__ = 'parcel_rates'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    rate_type = Column(String(50), nullable=False) # e.g., flat, per_kg, per_km
    rate = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
