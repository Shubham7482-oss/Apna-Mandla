from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from datetime import datetime, timedelta
import json

from app import crud, models, schemas
from app.core.database import get_db
from app.core.rbac import (
    require_shop_admin, 
    require_rider_admin, 
    require_content_admin, 
    require_super_admin,
    require_admin
)
from app.models.mini_website import MiniWebsite
from app.models.user import User
from app.models.ad import Ad
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.shop_profile import ShopProfile
from app.models.rider_profile import RiderProfile
from app.schemas.common import SuccessResponse

router = APIRouter()

@router.get("/pending-applications", response_model=List[schemas.RoleApplicationOut])
def get_pending_applications(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Retrieve all pending role applications.
    """
    applications = crud.crud_role_application.get_pending_applications(db)
    result = []
    for app in applications:
        app_out = schemas.RoleApplicationOut.from_orm(app)
        app_out.user_name = app.user.full_name
        result.append(app_out)
    return result

@router.post("/approve-application/{application_id}", response_model=schemas.RoleApplicationOut)
def approve_application(
    *,
    db: Session = Depends(get_db),
    application_id: int,
    current_user: User = Depends(require_admin),
):
    """
    Approve a role application.
    """
    application = crud.crud_role_application.get_application(db, application_id=application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    updated_application = crud.crud_role_application.update_application_status(
        db=db, db_obj=application, status="APPROVED"
    )

    user_to_update = crud.user.get(db, id=application.user_id)
    if user_to_update:
        new_roles = user_to_update.roles or []
        if application.requested_role not in new_roles:
            new_roles.append(application.requested_role)
            crud.user.update(db, db_obj=user_to_update, obj_in={"roles": new_roles})

    return updated_application

@router.patch("/website/{website_id}/verify")
def toggle_website_verification(
    website_id: int,
    verified: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_shop_admin),
):
    """
    Admin only: Verify or unverify a Mini Website.
    """
    website = db.query(MiniWebsite).filter(MiniWebsite.id == website_id).first()
    if not website:
        raise HTTPException(status_code=404, detail="Mini website not found")
    
    website.verified_badge = verified
    db.commit()
    db.refresh(website)
    
    return {"success": True, "message": f"Website verification set to {verified}", "is_verified": website.verified_badge}

@router.get("/ads/all")
def get_all_ads(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_content_admin)
):
    """Fetch all advertisements for admin review."""
    return db.query(Ad).order_by(Ad.created_at.desc()).all()

@router.patch("/ads/{ad_id}/status")
def update_ad_status(
    ad_id: int,
    is_active: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_content_admin)
):
    """Enable or Disable an advertisement."""
    ad = db.query(Ad).filter(Ad.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")
    ad.is_active = is_active
    db.commit()
    return {"success": True, "message": f"Ad status updated to {is_active}"}

@router.patch("/user/{user_id}/subscription")
def manage_user_subscription(
    user_id: int,
    plan_name: str = Body(..., embed=True),
    days: int = Body(30, embed=True),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_super_admin)
):
    """Manually assign or upgrade a user's subscription."""
    user = db.query(User).filter(User.id == user_id).first()
    plan = db.query(SubscriptionPlan).filter(func.upper(SubscriptionPlan.name) == plan_name.upper()).first()
    
    if not user or not plan:
        raise HTTPException(status_code=404, detail="User or Plan not found")

    new_sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status="ACTIVE",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=days)
    )
    db.add(new_sub)
    db.commit()
    return {"success": True, "message": f"User upgraded to {plan_name} for {days} days"}

@router.get("/kyc/{user_id}")
def get_user_kyc_details(
    user_id: int,
    db: Session = Depends(get_db),
    # Use require_admin first, then perform internal role logic
    current_admin: User = Depends(require_admin)
):
    """Fetch full KYC documents and info for a user based on admin field role."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Internal permission check based on target user type
    is_super = current_admin.user_type == "SUPER_ADMIN"
    admin_field = (getattr(current_admin, "admin_role", "") or "").upper()

    details = {}
    if user.user_type == "SELLER" or user.shop_profile:
        if not is_super and admin_field != "SHOP_ADMIN":
            raise HTTPException(status_code=403, detail="Need SHOP_ADMIN permissions")
            
        profile = db.query(ShopProfile).filter(ShopProfile.user_id == user_id).first()
        if profile:
            details = {
                "type": "SHOP",
                "business_name": profile.business_name,
                "aadhar_url": profile.aadhar_url,
                "pan_url": profile.pan_url,
                "shop_images": json.loads(profile.shop_images_json) if profile.shop_images_json else [],
                "lat": profile.latitude,
                "lng": profile.longitude,
                "status": profile.approval_status
            }
    elif user.user_type == "RIDER" or user.rider_profile:
        if not is_super and admin_field != "RIDER_ADMIN":
            raise HTTPException(status_code=403, detail="Need RIDER_ADMIN permissions")

        profile = db.query(RiderProfile).filter(RiderProfile.user_id == user_id).first()
        if profile:
            details = {
                "type": "RIDER",
                "name": user.name,
                "aadhar_url": profile.aadhar_url,
                "license_url": profile.license_url,
                "vehicle_photo": profile.vehicle_photo_url,
                "police_url": profile.police_verification_url,
                "tier": profile.verification_tier,
                "status": profile.status
            }
    
    return {"success": True, "data": details}