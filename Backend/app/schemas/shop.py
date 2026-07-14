from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


# ───────────────────────────────
# SHOP STATUS UPDATE
# ───────────────────────────────
class ShopStatusUpdate(BaseModel):
    is_open: bool
    # 'AVAILABLE', 'BUSY', 'CLOSED' etc.
    availability_status: Optional[str] = "OPEN" 


# ───────────────────────────────
# SHOP RESPONSE (For Owner/Admin)
# ───────────────────────────────
class ShopResponse(BaseModel):
    id: int
    user_id: int
    slug: str
    approval_status: str
    is_open: bool
    availability_status: str
    public_visible: bool
    
    # Optional fields for deeper info
    last_opened_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ───────────────────────────────
# SHOP PUBLIC VIEW (For Customers)
# ───────────────────────────────
class ShopPublicView(BaseModel):
    id: int
    slug: str
    # Note: Shop name usually comes from ShopProfile relation
    shop_name: Optional[str] = None 
    category_id: int
    is_open: bool
    availability_status: str
    
    # Instead of verified, we use approval_status in logic
    is_approved: bool = False 

    model_config = ConfigDict(from_attributes=True)


class ShopActivateResponse(BaseModel):
    shop_id: int
    message: str
    slug: str # Return slug so frontend can navigate