from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Dict, Any
from decimal import Decimal

from app.core.database import get_db
from app.models.ad import Ad
from app.models.shop import Shop
from app.models.user import User
from app.models.wallet import Wallet
from app.models.ledger_entry import LedgerEntry
from app.core.pincode import get_active_pincode
from app.models.pincode import Pincode
from app.schemas.common import SuccessResponse
from app.core.rbac import require_business_user
from app.core.feature_guard import check_feature_access

router = APIRouter(prefix="/ads", tags=["Advertisements"])

@router.get("/banners")
def get_area_banners(
    db: Session = Depends(get_db),
    pincode: Pincode = Depends(get_active_pincode)
):
    """
    Fetch active banner ads for the user's specific Mandla/Area.
    """
    now = datetime.utcnow()
    
    # Filter by Area (Mandla) and Expiry Date
    ads = db.query(Ad).filter(
        Ad.mandla_id == pincode.mandla_id,
        Ad.is_active == True,
        Ad.start_date <= now,
        Ad.end_date >= now
    ).all()

    banner_data = []
    for ad in ads:
        banner_data.append({
            "id": ad.id,
            "image_url": ad.image_url,
            "shop_slug": ad.shop.slug,
            "shop_id": ad.shop_id
        })

    return SuccessResponse(success=True, data=banner_data, message="Banners fetched")

@router.post("/click/{ad_id}")
def record_ad_click(ad_id: int, db: Session = Depends(get_db)):
    ad = db.query(Ad).filter(Ad.id == ad_id).first()
    if ad:
        ad.click_count += 1
        db.commit()
    return {"success": True}

@router.post("/create", response_model=SuccessResponse)
def create_ad(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_business_user)
):
    # 1. Define Pricing
    prices = {"DAILY": 50.0, "WEEKLY": 300.0, "MONTHLY": 1000.0}
    duration = payload.get("duration", "DAILY")
    cost = Decimal(str(prices.get(duration, 50.0)))

    # 2. Check Wallet Balance
    wallet = db.query(Wallet).filter(Wallet.user_id == current_user.id).first()
    if not wallet or wallet.balance < cost:
        raise HTTPException(status_code=400, detail=f"Insufficient wallet balance. You need ₹{cost}")

    # 3. Deduct Balance & Log Ledger
    wallet.balance -= cost
    db.add(LedgerEntry(
        wallet_id=wallet.id,
        entry_type="DEBIT",
        amount=cost,
        description=f"Ad Booking - {duration} Plan"
    ))

    # 4. Create Ad Record
    if not current_user.owned_shop:
        raise HTTPException(status_code=404, detail="Shop profile not found")
    
    shop = current_user.owned_shop[0]
    days = {"DAILY": 1, "WEEKLY": 7, "MONTHLY": 30}[duration]
    
    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=days)

    new_ad = Ad(
        shop_id=shop.id,
        mandla_id=shop.profile.mandla_id if shop.profile else 1, # Using linked profile's area
        image_url=payload.get("image_url"),
        start_date=start_date,
        end_date=end_date,
        is_active=True
    )

    db.add(new_ad)
    db.commit()
    
    return SuccessResponse(success=True, data={"new_balance": float(wallet.balance)}, message=f"Ad booked and ₹{cost} deducted.")

@router.get("/my-ads")
def get_my_ads(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_business_user)
):
    if not current_user.owned_shop:
        raise HTTPException(status_code=404, detail="No shop found for this user")
        
    shop_id = current_user.owned_shop[0].id
    ads = db.query(Ad).filter(Ad.shop_id == shop_id).order_by(Ad.created_at.desc()).all()
    
    return SuccessResponse(success=True, data=ads, message="My ads fetched")