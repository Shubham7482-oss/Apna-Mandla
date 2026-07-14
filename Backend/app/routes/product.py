from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.feature_guard import get_active_subscription
from app.core.pincode import get_active_pincode

from app.models.mandla import Mandla
from app.models.pincode import Pincode
from app.models.shop import Shop
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductCreate, ProductResponse

# ✅ THIS WAS MISSING
router = APIRouter(
    prefix="/products",
    tags=["Products"],
)

# ───────────────────────────────
# ➕ CREATE PRODUCT
# ───────────────────────────────
@router.post(
    "/create",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = db.query(Shop).filter(Shop.id == data.shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop nahi mili")

    if shop.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Aap is dukan ke malik nahi hain")

    if shop.approval_status != "APPROVED":
        raise HTTPException(
            status_code=403,
            detail=f"Aapki dukan abhi {shop.approval_status} hai. Approve hone ka intezar karein.",
        )

    current_product_count = db.query(Product).filter(
        Product.shop_id == data.shop_id,
        Product.is_archived == False,
    ).count()

    subscription = get_active_subscription(shop)
    max_limit = subscription.plan.max_products if subscription else 5

    if current_product_count >= max_limit:
        raise HTTPException(
            status_code=403,
            detail=f"Limit khatam! Aap sirf {max_limit} items dal sakte hain. Plan upgrade karein.",
        )

    new_product = Product(
        shop_id=data.shop_id,
        category_id=data.category_id,
        name=data.name,
        description=data.description,
        unit=data.unit,
        price=data.price,
        discount_price=data.discount_price,
        image_url=data.image_url,
        stock_quantity=data.stock_quantity,
        manage_stock=data.manage_stock,
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return new_product


# ───────────────────────────────
# 📋 LIST PRODUCTS
# ───────────────────────────────
@router.get("/shop/{shop_id}", response_model=List[ProductResponse])
def list_products(
    shop_id: int,
    db: Session = Depends(get_db),
    pincode: Pincode = Depends(get_active_pincode),
):
    shop = db.query(Shop).filter(
        Shop.id == shop_id,
        Shop.is_archived == False,
    ).first()

    if not shop or not shop.profile:
        raise HTTPException(status_code=404, detail="Shop not found")

    mandla = db.query(Mandla).filter(
        Mandla.id == shop.profile.mandla_id,
        Mandla.is_active == True,
    ).first()

    if not mandla or mandla.id != pincode.mandla_id:
        raise HTTPException(
            status_code=403,
            detail="Shop not available for this pincode",
        )

    products = db.query(Product).filter(
        Product.shop_id == shop_id,
        Product.is_archived == False,
        Product.is_available == True,
    ).all()

    return products


# ───────────────────────────────
# ❌ DELETE PRODUCT (Soft Delete)
# ───────────────────────────────
@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product nahi mila")

    shop = db.query(Shop).filter(Shop.id == product.shop_id).first()

    if shop.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Unauthorized access")

    product.is_archived = True
    db.commit()

    return {"message": "Product archive kar diya gaya hai"}