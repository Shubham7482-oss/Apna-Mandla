from pydantic import BaseModel


class DiscountCreate(BaseModel):
    product_id: int
    percentage: float


class DiscountResponse(BaseModel):
    id: int
    product_id: int
    percentage: float
    is_active: bool

    class Config:
        orm_mode = True