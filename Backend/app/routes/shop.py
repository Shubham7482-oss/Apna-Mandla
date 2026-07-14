from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from datetime import datetime
from slugify import slugify

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.pincode import get_active_pincode
from app.core.rbac import require_content_admin

from app.models.mandla import Mandla
from app.models.pincode import Pincode
from app.models.shop import Shop
from app.models.shop_profile import ShopProfile
from app.models.order import Order
from app.models.user import User
from app.models.shop_category import ShopCategory

from app.services.broadcast_service import start_broadcast

router = APIRouter(prefix="/shops", tags=["Shops"])


# =========================================================
# ROLE CHECK
# =========================================================
def ensure_seller(db: Session, user: User):
    shop = db.query(Shop).filter(
        Shop.user_id == user.id,
        Shop.is_archived == False
    ).first()

    if not shop:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a seller",
        )

    return shop


# =========================================================
# BECOME SELLER
# =========================================================
@router.post("/become-seller", status_code=status.HTTP_201_CREATED)
def become_seller(
    shop_name: str,
    category_id: int,
    mandla_id: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    existing_shop = db.query(Shop).filter(
        Shop.user_id == current_user.id,
        Shop.is_archived == False
    ).first()

    if existing_shop:
        raise HTTPException(
            status_code=400,
            detail="User already has a shop",
        )

    now = datetime.utcnow()

    profile = ShopProfile(
        user_id=current_user.id,
        mandla_id=mandla_id,
        business_name=shop_name,
        category=str(category_id),
        approval_status="PENDING",
        is_active=True,
        is_archived=False,
        created_at=now,
        updated_at=now,
    )

    db.add(profile)
    db.flush()

    base_slug = slugify(shop_name)
    slug = base_slug
    counter = 1

    while db.query(Shop).filter(Shop.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    shop = Shop(
        user_id=current_user.id,
        shop_profile_id=profile.id,
        category_id=category_id,
        slug=slug,
        approval_status="PENDING",
        public_visible=False,
        suspended=False,
        is_open=False,
        availability_status="CLOSED",
        is_archived=False,
        created_at=now,
        updated_at=now,
    )

    db.add(shop)
    db.commit()
    db.refresh(shop)

    return {
        "message": "Shop created. Awaiting admin approval.",
        "shop_id": shop.id,
        "slug": slug,
    }


# =========================================================
# PUBLIC SHOP LIST
# =========================================================
@router.get("")
def list_shops(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    pincode: Pincode = Depends(get_active_pincode),
):

    mandla = db.query(Mandla).filter(
        Mandla.id == pincode.mandla_id,
        Mandla.is_active == True,  # noqa: E712
    ).first()
    if not mandla:
        raise HTTPException(status_code=403, detail="Mandla not active for this pincode")

    query = (
        db.query(Shop)
        .join(ShopProfile, Shop.shop_profile_id == ShopProfile.id)
        .filter(
            Shop.is_archived == False,           # noqa: E712
            Shop.public_visible == True,        # noqa: E712
            Shop.approval_status == "APPROVED",
            ShopProfile.is_archived == False,   # noqa: E712
            ShopProfile.mandla_id == pincode.mandla_id,
        )
    )

    if category:
        query = query.filter(ShopProfile.category.ilike(f"%{category}%"))

    if search:
        query = query.filter(ShopProfile.business_name.ilike(f"%{search}%"))

    total = query.count()
    shops = (
        query.order_by(ShopProfile.business_name.asc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return {
        "items": [
            {
                "shop_id": shop.id,
                "business_name": shop.profile.business_name,
                "category": shop.profile.category,
                "is_open": shop.is_open,
                "availability_status": shop.availability_status,
            }
            for shop in shops
        ],
        "total": total,
        "page": page,
        "size": size,
    }


# =========================================================
# GET MY SHOP
# =========================================================
@router.get("/me")
def get_my_shop(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = ensure_seller(db, current_user)
    profile = shop.profile

    return {
        "shop": {
            "id": shop.id,
            "approval_status": shop.approval_status,
            "public_visible": shop.public_visible,
            "is_open": shop.is_open,
            "availability_status": shop.availability_status,
            "business_name": profile.business_name,
            "category": profile.category,
        }
    }


# =========================================================
# SET SHOP STATUS
# =========================================================
@router.post("/{shop_id}/status")
def set_shop_status(
    shop_id: int,
    is_open: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    shop = db.query(Shop).filter(
        Shop.id == shop_id,
        Shop.user_id == current_user.id,
        Shop.is_archived == False,
        Shop.approval_status == "APPROVED",
    ).first()

    if not shop:
        raise HTTPException(
            status_code=404,
            detail="Shop not found or not approved",
        )

    if shop.suspended:
        raise HTTPException(
            status_code=403,
            detail="Shop is suspended",
        )

    now = datetime.utcnow()

    shop.is_open = is_open
    shop.availability_status = "OPEN" if is_open else "CLOSED"
    shop.updated_at = now

    if is_open:
        shop.last_opened_at = now
    else:
        shop.last_closed_at = now

    db.commit()

    return {
        "message": "Shop status updated",
        "shop_id": shop.id,
        "is_open": shop.is_open,
    }


# =========================================================
# START ORDER BROADCAST
# =========================================================
@router.post("/orders/{order_id}/broadcast")
def shop_start_order_broadcast(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    shop = ensure_seller(db, current_user)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.shop_id == shop.id,
            Order.is_archived == False,
        )
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if order.status != "READY_FOR_PICKUP":
        raise HTTPException(
            status_code=400,
            detail="Order must be READY_FOR_PICKUP"
        )

    updated_order = start_broadcast(db, order.id)

    return {
        "message": "Broadcast started",
        "order_id": updated_order.id,
        "status": updated_order.status,
        "deadline": updated_order.broadcast_deadline,
    }


# =========================================================
# PUBLIC SHOP VIEW
# =========================================================
@router.get("/{shop_id}/public")
def public_shop_view(
    shop_id: int,
    db: Session = Depends(get_db),
):

    shop = db.query(Shop).filter(
        Shop.id == shop_id,
        Shop.is_archived == False,
        Shop.public_visible == True,
        Shop.approval_status == "APPROVED",
    ).first()

    if not shop:
        raise HTTPException(
            status_code=404,
            detail="Shop not found",
        )

    profile = shop.profile

    return {
        "shop_id": shop.id,
        "business_name": profile.business_name,
        "category": profile.category,
        "is_open": shop.is_open,
        "availability_status": shop.availability_status,
        "slug": shop.slug,
    }


# =========================================================
# LOOKUP SHOP BY UNIQUE ID (QR CODE)
# =========================================================
@router.get("/lookup/{unique_id}")
def lookup_shop_by_qr(unique_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.unique_id == unique_id).first()
    if not user or not user.owned_shop:
        raise HTTPException(status_code=404, detail="Shop not found for this QR")
    
    shop = user.owned_shop[0]
    return {"id": shop.id, "slug": shop.slug, "name": shop.custom_display_name or user.name}


# =========================================================
# CONTENT_ADMIN CATEGORY MANAGEMENT
# =========================================================
@router.post("/categories")
def create_category(
    name: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_content_admin)
):
    """CONTENT_ADMIN: Create a new shop category."""
    new_cat = ShopCategory(name=name)
    db.add(new_cat)
    db.commit()
    return {"success": True, "message": f"Category {name} created"}

@router.delete("/categories/{cat_id}")
def delete_category(
    cat_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_content_admin)
):
    """CONTENT_ADMIN: Delete a shop category."""
    cat = db.query(ShopCategory).filter(ShopCategory.id == cat_id).first()
    if not cat: raise HTTPException(404, "Category not found")
    db.delete(cat)
    db.commit()
    return {"success": True, "message": "Category deleted"}