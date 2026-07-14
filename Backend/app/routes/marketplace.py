
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
import json

from app.core.database import get_db
from app.core.feature_guard import check_feature_access
from app.core.pincode import get_active_pincode

from app.models.mandla import Mandla
from app.models.pincode import Pincode
from app.models.shop import Shop
from app.models.shop_profile import ShopProfile
from app.models.product import Product
from app.services.shop_engine import ShopEngine

router = APIRouter(prefix="/marketplace", tags=["Marketplace"])


@router.get("/shops")
def list_shops(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    pincode: Pincode = Depends(get_active_pincode),
):
    """
    Marketplace API with Premium Priority Boost, scoped by active pincode.
    """
    # 1. Ensure Mandla is active for this pincode
    mandla = db.query(Mandla).filter(
        Mandla.id == pincode.mandla_id,
        Mandla.is_active == True,  # noqa: E712
    ).first()
    if not mandla:
        raise HTTPException(status_code=403, detail="Mandla not active for this pincode")

    base_query = (
        db.query(Shop)
        .join(ShopProfile, Shop.id == ShopProfile.shop_id)
        .filter(
            Shop.public_visible == True,  # noqa: E712
            Shop.suspended == False,      # noqa: E712
            Shop.approval_status == "APPROVED",
            Shop.is_archived == False,    # noqa: E712
            ShopProfile.mandla_id == pincode.mandla_id,
        )
    )

    total = base_query.count()
    shops = (
        base_query
        .order_by(Shop.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = []
    for shop in shops:
        avg_rating, total_ratings = ShopEngine.get_rating_summary(db, shop.id)
        tier = ShopEngine.get_website_tier(db, shop.id)
        base_score = ShopEngine.calculate_shop_score(db, shop)
        premium_status = check_feature_access(shop)
        premium_boost = 50 if premium_status else 0
        final_score = base_score + premium_boost

        items.append(
            {
                "id": shop.id,
                "name": shop.profile.business_name if shop.profile else "Unknown Shop",
                "slug": shop.slug,
                "logo": shop.profile.shop_logo if shop.profile else None,
                "category": shop.profile.category if shop.profile else "General",
                "is_open": shop.is_open,
                "rating": avg_rating,
                "total_ratings": total_ratings,
                "website_tier": tier,
                "is_premium": premium_status,
                "final_score": final_score,
                "availability_status": shop.availability_status,
            }
        )

    # Sort page results by score
    items.sort(key=lambda x: x["final_score"], reverse=True)

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/shops/{shop_id}/products")
def list_shop_products(
    shop_id: int,
    db: Session = Depends(get_db),
):
    """
    Fetch all active products for a specific approved shop.
    """
    shop = db.query(Shop).filter(
        Shop.id == shop_id,
        Shop.approval_status == "APPROVED",
        Shop.is_archived == False
    ).first()

    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found or not approved")

    products = db.query(Product).filter(
        Product.shop_id == shop_id,
        Product.is_active == True,
        Product.is_archived == False
    ).all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "price": p.current_price,
            "stock": p.stock_quantity,
            "imageUrl": p.image_url,
            "unit": p.unit
        }
        for p in products
    ]


@router.get("/search")
def global_search(
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    pincode: Pincode = Depends(get_active_pincode)
):
    """
    Global search for shops and products within the active Mandla.
    """
    # 1. Search Shops in this Mandla
    shops = db.query(ShopProfile).filter(
        ShopProfile.mandla_id == pincode.mandla_id,
        or_(
            ShopProfile.business_name.ilike(f"%{q}%"),
            ShopProfile.category.ilike(f"%{q}%")
        )
    ).all()

    # 2. Search Products in this Mandla
    products = db.query(Product).join(Shop).join(ShopProfile).filter(
        ShopProfile.mandla_id == pincode.mandla_id,
        or_(
            Product.name.ilike(f"%{q}%"),
            Product.description.ilike(f"%{q}%")
        )
    ).all()

    return {
        "success": True,
        "results": {
            "shops": [
                {
                    "id": s.id,
                    "business_name": s.business_name,
                    "category": s.category,
                    "logo_url": s.logo_url
                } for s in shops
            ],
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "price": float(p.price),
                    "image_url": p.image_url,
                    "shop_id": p.shop_id
                } for p in products
            ]
        }
    }
