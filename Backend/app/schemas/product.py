from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from decimal import Decimal
from datetime import datetime


# ───────────────────────────────
# PRODUCT BASE (Shared Fields)
# ───────────────────────────────
class ProductBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = None
    
    # Financials (Using Decimal for precision)
    price: Decimal = Field(..., gt=0)
    discount_price: Optional[Decimal] = Field(None, ge=0)
    
    # Inventory
    unit: str = Field("piece", description="e.g., kg, gram, packet, piece")
    stock_quantity: int = Field(0, ge=0)
    is_available: bool = True


# ───────────────────────────────
# CREATE / UPDATE SCHEMA
# ───────────────────────────────
class ProductCreate(ProductBase):
    category_id: Optional[int] = None
    shop_id: int


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    discount_price: Optional[Decimal] = None
    unit: Optional[str] = None
    stock_quantity: Optional[int] = None
    is_available: Optional[bool] = None
    category_id: Optional[int] = None


# ───────────────────────────────
# RESPONSE SCHEMA
# ───────────────────────────────
class ProductResponse(ProductBase):
    id: int
    shop_id: int
    category_id: Optional[int] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime

    # ✅ Crucial for SQLAlchemy compatibility
    model_config = ConfigDict(from_attributes=True)


# ───────────────────────────────
# LIST VIEW (Optional: For fast loading)
# ───────────────────────────────
class ProductListResponse(BaseModel):
    total: int
    items: List[ProductResponse]