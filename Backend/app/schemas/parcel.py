from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.parcel import ParcelStatus, PaymentMode

class ParcelBase(BaseModel):
    recipient_name: str
    recipient_phone: str
    pickup_address: str
    dropoff_address: str
    pickup_plus_code: Optional[str] = None
    dropoff_plus_code: Optional[str] = None
    parcel_description: Optional[str] = None
    payment_mode: PaymentMode

class ParcelCreate(ParcelBase):
    pass

class ParcelUpdate(BaseModel):
    weight: Optional[float] = None
    height: Optional[float] = None
    distance: Optional[float] = None
    rate: Optional[float] = None

class ParcelInDBBase(ParcelBase):
    id: int
    sender_id: int
    status: ParcelStatus
    delivery_fee: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Parcel(ParcelInDBBase):
    pass
