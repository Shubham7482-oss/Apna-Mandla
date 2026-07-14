from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Dict, Any, List

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.shop_profile import ShopProfile
from app.models.rider_profile import RiderProfile
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/kyc", tags=["KYC & Verification"])

@router.post("/shop-submit")
def submit_shop_kyc(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    shop = db.query(ShopProfile).filter(ShopProfile.user_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop profile not found")

    shop.aadhar_url = payload.get("aadhar_url")
    shop.pan_url = payload.get("pan_url")
    shop.shop_images_json = payload.get("shop_images") # Expecting JSON list
    shop.plus_code = payload.get("plus_code")
    shop.approval_status = "PENDING"
    
    db.commit()
    return SuccessResponse(success=True, message="KYC submitted for review")

@router.post("/rider-submit")
def submit_rider_kyc(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rider = db.query(RiderProfile).filter(RiderProfile.user_id == current_user.id).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")

    rider.aadhar_url = payload.get("aadhar_url")
    rider.license_url = payload.get("license_url")
    rider.vehicle_photo_url = payload.get("vehicle_photo_url")
    
    # Optional Police Verification for upgrade to FULL tier
    if payload.get("police_verification_url"):
        rider.police_verification_url = payload.get("police_verification_url")
        rider.verification_tier = "FULL"
    else:
        rider.verification_tier = "NORMAL"

    rider.status = "PENDING"
    db.commit()
    return SuccessResponse(success=True, message="Rider KYC submitted for review")
