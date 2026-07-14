from pydantic import BaseModel

class ParcelRateBase(BaseModel):
    rate_per_km: float
    base_fare: float
    min_delivery_charge: float

class ParcelRateCreate(ParcelRateBase):
    pass

class ParcelRateUpdate(ParcelRateBase):
    pass

class ParcelRate(ParcelRateBase):
    id: int

    class Config:
        from_attributes = True
