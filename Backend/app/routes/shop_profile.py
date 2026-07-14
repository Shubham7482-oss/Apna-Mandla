# app/routes/shop_profile.py

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import json

from app.core.database import get_db
from app.core.rbac import require_shop
from app.core.feature_guard import check_feature_access

from app.models.shop_profile import ShopProfile
from app.models.shop import Shop
from app.models.mandla import Mandla
from app.models.user import User

router = APIRouter(prefix="/shops", tags=["Shops"])


# ───────────────────────────────
# CREATE / UPDATE MY SHOP PROFILE
# ───────────────────────────────
@router.post("/me")
def create_or_update_my_shop(
    business_name: str,
    category: str,
    mandla_id: int,
    address: str | None = None,
    current_user: User = Depends(require_shop),
    db: Session = Depends(get_db),
):
    mandla = (
        db.query(Mandla)
        .filter(
            Mandla.id == mandla_id,
            Mandla.is_active == True,
            Mandla.is_archived == False,
        )
        .first()
    )

    if not mandla:
        raise HTTPException(status_code=404, detail="Mandla not found")

    shop = (
        db.query(ShopProfile)
        .filter(
            ShopProfile.user_id == current_user.id,
            ShopProfile.is_archived == False,
        )
        .first()
    )

    if shop:
        shop.business_name = business_name
        shop.category = category
        shop.address = address
        shop.mandla_id = mandla.id
    else:
        shop = ShopProfile(
            user_id=current_user.id,
            business_name=business_name,
            category=category,
            address=address,
            mandla_id=mandla.id,
            approval_status="PENDING",
            is_active=False,
            is_archived=False,
        )
        db.add(shop)

    db.commit()
    db.refresh(shop)

    return {
        "message": "Shop profile saved",
        "shop": {
            "id": shop.id,
            "business_name": shop.business_name,
            "category": shop.category,
            "address": shop.address,
            "mandla_id": shop.mandla_id,
        },
    }


# ───────────────────────────────
# GET MY SHOP PROFILE
# ───────────────────────────────
@router.get("/me")
def get_my_shop(
    current_user: User = Depends(require_shop),
    db: Session = Depends(get_db),
):
    shop = (
        db.query(ShopProfile)
        .filter(
            ShopProfile.user_id == current_user.id,
            ShopProfile.is_archived == False,
        )
        .first()
    )

    if not shop:
        return {"shop": None}

    return {
        "shop": {
            "id": shop.id,
            "business_name": shop.business_name,
            "category": shop.category,
            "address": shop.address,
            "mandla_id": shop.mandla_id,
        }
    }


# ───────────────────────────────
# CUSTOMER DISCOVERY (FINAL FIXED VERSION)
# ───────────────────────────────
@router.get("")
def discover_shops(
    mandla_id: int,
    category: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    query = (
        db.query(Shop, ShopProfile)
        .join(ShopProfile, Shop.shop_profile_id == ShopProfile.id)
        .filter(
            Shop.approval_status == "APPROVED",
            Shop.public_visible == True,
            Shop.is_archived == False,
            ShopProfile.mandla_id == mandla_id,
            ShopProfile.is_archived == False,
        )
    )

    if category:
        query = query.filter(ShopProfile.category.ilike(f"%{category}%"))

    if search:
        query = query.filter(ShopProfile.business_name.ilike(f"%{search}%"))

    results = query.order_by(ShopProfile.business_name.asc()).all()

    return [
        {
            "id": profile.id,
            "business_name": profile.business_name,
            "category": profile.category,
            "address": profile.address,
        }
        for shop, profile in results
    ]


@router.patch("/branding")
def update_shop_branding(
    logo_url: Optional[str] = Body(None),
    banner_url: Optional[str] = Body(None),
    current_user: User = Depends(require_shop),
    db: Session = Depends(get_db),
):
    # MANDATORY SILVER CHECK
    if not check_feature_access(current_user, "SILVER"):
        raise HTTPException(status_code=403, detail="Logo and Banner branding requires a SILVER or GOLD subscription.")

    shop = db.query(ShopProfile).filter(ShopProfile.user_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop profile not found")

    if logo_url is not None:
        shop.logo_url = logo_url
    if banner_url is not None:
        shop.banner_url = banner_url

    db.commit()
    db.refresh(shop)

    return {
        "success": True,
        "message": "Branding updated",
        "data": {"logo_url": shop.logo_url, "banner_url": shop.banner_url}
    }


@router.patch("/bank-details")
def update_bank_details(
    account_number: str = Body(...),
    ifsc_code: str = Body(...),
    holder_name: str = Body(...),
    bank_name: str = Body(...),
    current_user: User = Depends(require_shop),
    db: Session = Depends(get_db),
):
    shop = db.query(ShopProfile).filter(ShopProfile.user_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop profile not found")

    # 🛑 SECURITY CHECK: Only approved shops can add bank details
    if shop.approval_status != "APPROVED":
        raise HTTPException(
            status_code=403,
            detail="You can only add bank details after your shop is APPROVED by admin."
        )

    bank_info = {
        "account_number": account_number,
        "ifsc_code": ifsc_code,
        "holder_name": holder_name,
        "bank_name": bank_name,
        "updated_at": datetime.utcnow().isoformat()
    }

    shop.bank_details_json = json.dumps(bank_info)
    db.commit()

    return {"success": True, "message": "Bank details updated successfully"}