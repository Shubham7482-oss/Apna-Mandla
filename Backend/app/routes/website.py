from fastapi import APIRouter, Request, HTTPException, Depends, Body, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Any, Optional
import json

from app.core.database import get_db
from app.core.rbac import require_business_user
from app.models.mini_website import MiniWebsite
from app.models.user import User
from app.models.rating import Rating
from app.models.shop_profile import ShopProfile
from app.models.discount import DiscountRule
from app.utils.qr_generator import generate_qr
from app.schemas.common import SuccessResponse
from app.core.feature_guard import check_feature_access, get_active_subscription

router = APIRouter()  # ⚠️ IMPORTANT: No prefix here (handled in main.py)

templates = Jinja2Templates(directory="app/templates")


# ==========================================================
# 🔹 DRAWER DATA API
# ==========================================================
@router.get(
    "/drawer-data",
    response_model=SuccessResponse[Dict[str, Any]],
)
def drawer_data(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_business_user),
):
    """
    Returns all side drawer related information.
    Only CUSTOMER / SHOP / RIDER allowed.
    """

    # Prevent caching (important for wallet balance freshness)
    response.headers["Cache-Control"] = "no-store"

    website = (
        db.query(MiniWebsite)
        .filter(
            MiniWebsite.user_id == current_user.id,
            MiniWebsite.is_archived == False,
        )
        .first()
    )

    # 🔥 Auto-generate QR if missing
    if not current_user.qr_code_url:
        qr_path = generate_qr(current_user.unique_id)
        current_user.qr_code_url = qr_path
        db.commit()
        db.refresh(current_user)

    data = {
        "name": current_user.name,
        "user_type": current_user.user_type,
        "wallet_balance": current_user.wallet_balance,
        "qr_code_url": current_user.qr_code_url,
        "website_slug": website.slug if website else None,
        "is_open": website.is_open if website else False,
    }

    return SuccessResponse(
        success=True,
        data=data,
        message="Drawer data fetched successfully",
    )


# ==========================================================
# 🔹 GET MY WEBSITE DETAILS
# ==========================================================
@router.get(
    "/my-website",
    response_model=SuccessResponse[Dict[str, Any]],
)
def get_my_website(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_business_user),
):
    """
    Get the mini website details for the current user.
    """
    website = db.query(MiniWebsite).filter(MiniWebsite.user_id == current_user.id).first()
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")

    # Get active plan
    sub = get_active_subscription(current_user)
    current_plan = sub.plan.name.upper() if sub else "BASIC"

    # Calculate ratings
    rating_target = current_user.user_type.upper()
    if rating_target == "SELLER": rating_target = "SHOP"
    stats = db.query(
        func.avg(Rating.rating).label("avg_rating"),
        func.count(Rating.id).label("total_reviews")
    ).filter(
        Rating.target_id == current_user.id,
        Rating.target_type == rating_target
    ).first()

    data = {
        "id": website.id,
        "display_name": website.display_name,
        "slug": website.slug,
        "short_bio": website.short_bio,
        "description": website.description,
        "profile_photo_url": website.profile_photo_url,
        "cover_photo_url": website.cover_photo_url,
        "is_open": website.is_open,
        "public_visible": website.public_visible,
        "availability_status": website.availability_status,
        "average_rating": round(stats.avg_rating or 0.0, 1),
        "total_reviews": stats.total_reviews or 0,
        "current_plan": current_plan,
        "facebook_url": website.facebook_url,
        "instagram_url": website.instagram_url,
        "twitter_url": website.twitter_url,
        "youtube_url": website.youtube_url,
    }

    return SuccessResponse(success=True, data=data, message="Website details fetched")


# ==========================================================
# 🔹 UPDATE MY WEBSITE DETAILS
# ==========================================================
@router.patch(
    "/my-website",
    response_model=SuccessResponse[Dict[str, Any]],
)
def update_mini_website(
    display_name: Optional[str] = Body(None),
    short_bio: Optional[str] = Body(None),
    description: Optional[str] = Body(None),
    slug: Optional[str] = Body(None),
    facebook_url: Optional[str] = Body(None),
    instagram_url: Optional[str] = Body(None),
    twitter_url: Optional[str] = Body(None),
    youtube_url: Optional[str] = Body(None),
    public_visible: Optional[bool] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_business_user),
):
    website = db.query(MiniWebsite).filter(MiniWebsite.user_id == current_user.id).first()
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")

    # 1. Check for GOLD features (Slug and Social Links)
    gold_features = [slug, facebook_url, instagram_url, twitter_url, youtube_url]
    if any(x is not None for x in gold_features):
        if not check_feature_access(current_user, "GOLD"):
            raise HTTPException(status_code=403, detail="Custom Slug and Social Links require a GOLD subscription.")

    # 2. Apply updates if allowed
    if display_name is not None: website.display_name = display_name
    if short_bio is not None: website.short_bio = short_bio
    if description is not None: website.description = description
    
    if slug is not None:
        # Check if slug is unique
        existing = db.query(MiniWebsite).filter(MiniWebsite.slug == slug, MiniWebsite.id != website.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="This URL slug is already taken.")
        website.slug = slug

    if facebook_url is not None: website.facebook_url = website.facebook_url
    if instagram_url is not None: website.instagram_url = website.instagram_url
    if twitter_url is not None: website.twitter_url = website.twitter_url
    if youtube_url is not None: website.youtube_url = website.youtube_url
    if public_visible is not None: website.public_visible = public_visible

    db.commit()
    db.refresh(website)

    return SuccessResponse(
        success=True,
        data={
            "id": website.id,
            "display_name": website.display_name,
            "slug": website.slug,
            "facebook_url": website.facebook_url,
            "instagram_url": website.instagram_url,
            "twitter_url": website.twitter_url,
            "youtube_url": website.youtube_url,
        },
        message="Website details updated successfully"
    )


# ==========================================================
# 🔹 TOGGLE MY WEBSITE STATUS
# ==========================================================
@router.patch(
    "/my-website/toggle-status",
    response_model=SuccessResponse[Dict[str, Any]],
)
def toggle_status(
    is_open: bool = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_business_user),
):
    """
    Toggle availability of My Website.
    Only CUSTOMER / SHOP / RIDER allowed.
    """

    website = (
        db.query(MiniWebsite)
        .filter(
            MiniWebsite.user_id == current_user.id,
            MiniWebsite.is_archived == False,
        )
        .first()
    )

    if not website:
        raise HTTPException(status_code=404, detail="Website not found")

    website.is_open = is_open
    website.availability_status = "AVAILABLE" if is_open else "CLOSED"

    db.commit()
    db.refresh(website)

    data = {
        "is_open": website.is_open,
        "availability_status": website.availability_status,
    }

    return SuccessResponse(
        success=True,
        data=data,
        message="Website status updated successfully",
    )


# ==========================================================
# 🔹 PUBLIC MY WEBSITE
# ==========================================================
@router.get("/public/{slug}", response_class=HTMLResponse)
def public_website(slug: str, request: Request, db: Session = Depends(get_db)):
    """
    Public facing My Website.
    Accessible via:
    /api/v1/website/public/{slug}
    """
    website = db.query(MiniWebsite).filter(MiniWebsite.slug == slug, MiniWebsite.public_visible == True, MiniWebsite.is_archived == False).first()
    if not website: raise HTTPException(status_code=404, detail="Website not found")

    user = db.query(User).filter(User.id == website.user_id).first()
    shop_profile = db.query(ShopProfile).filter(ShopProfile.user_id == user.id).first()
    
    # Fetch Active Offers (GOLD feature but visible to everyone on public site)
    offers = db.query(DiscountRule).filter(
        DiscountRule.shop_id == shop_profile.id, 
        DiscountRule.is_active == True
    ).all()

    # Subscription and Plan logic
    sub = get_active_subscription(user)
    plan = sub.plan.name.upper() if sub else "BASIC"
    
    # Calculate ratings
    rating_target = user.user_type.upper()
    if rating_target == "SELLER": rating_target = "SHOP"
    stats = db.query(
        func.avg(Rating.rating),
        func.count(Rating.id)
    ).filter(
        Rating.target_id == user.id,
        Rating.target_type == rating_target
    ).first()

    return templates.TemplateResponse(
        "mini_website.html",
        {
            "request": request,
            "website": website,
            "user": user,
            "shop_profile": shop_profile,
            "plan": plan,
            "offers": offers,
            "average_rating": round(stats[0] or 0.0, 1),
            "total_reviews": stats[1] or 0,
            "banners": json.loads(website.banner_images_json) if website.banner_images_json else [],
            "gallery": json.loads(website.gallery_images_json) if website.gallery_images_json else []
        },
    )