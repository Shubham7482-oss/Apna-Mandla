import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.shop import Shop
from app.models.shop_profile import ShopProfile
from pydantic import BaseModel, Field

router = APIRouter(prefix="/shop-register", tags=["Shop Registration"])

# ───────────────────────────────
# INPUT SCHEMA
# ───────────────────────────────
class ShopRegistrationRequest(BaseModel):
    shop_name: str = Field(..., min_length=3, max_length=100)
    category_id: int
    address: str
    description: Optional[str] = None
    plus_code: Optional[str] = None

# ───────────────────────────────
# HELPER: SLUG GENERATOR
# ───────────────────────────────
def generate_slug(name: str, db: Session):
    # Convert name to slug (e.g., "Sharma Kirana" -> "sharma-kirana")
    base_slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    slug = base_slug
    counter = 1
    # Check if slug exists, if yes, add number (sharma-kirana-1)
    while db.query(Shop).filter(Shop.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug

# ───────────────────────────────
# ROUTE: BECOME A SELLER
# ───────────────────────────────
@router.post("/enroll")
def enroll_as_seller(
    data: ShopRegistrationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Check if user already has a shop
    existing_shop = db.query(Shop).filter(Shop.user_id == current_user.id).first()
    if existing_shop:
        return {
            "message": "Aapki shop registration pehle se exist karti hai",
            "status": existing_shop.approval_status,
            "shop_id": existing_shop.id
        }

    # 2. Create Shop Profile first
    new_profile = ShopProfile(
        name=data.shop_name,
        address=data.address,
        description=data.description,
        plus_code=data.plus_code
    )
    db.add(new_profile)
    db.flush() # ID lene ke liye

    # 3. Create Shop Entry
    new_shop = Shop(
        user_id=current_user.id,
        shop_profile_id=new_profile.id,
        category_id=data.category_id,
        slug=generate_slug(data.shop_name, db),
        approval_status="PENDING", # Admin verify karega
        is_open=False,
        public_visible=False
    )
    
    db.add(new_shop)
    db.commit()

    return {
        "message": "Shop registration submitted! Admin approval ka intezar karein.",
        "shop_id": new_shop.id,
        "slug": new_shop.slug
    }

# Fix 2: Pydantic V2 Swagger error se bachne ke liye rebuild
ShopRegistrationRequest.model_rebuild()
