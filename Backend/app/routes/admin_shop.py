
from fastapi import APIRouter, Depends, HTTPException, Body, Request
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.core.rbac import require_super_admin, require_shop_admin
from app.models.user import User
from app.models.shop import Shop
from app.models.shop_profile import ShopProfile
from app.services.ledger_service import LedgerService
from app.services.admin_audit_service import log_admin_action

router = APIRouter(
    prefix="/admin/shops",
    tags=["Admin - Shops"],
    dependencies=[Depends(require_shop_admin)] # Protect the whole router
)


@router.get("/pending", response_model=None)
def list_pending_shops(
    admin: User = Depends(require_shop_admin),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Shop)
        .join(ShopProfile, Shop.shop_profile_id == ShopProfile.id)
        .filter(
            Shop.approval_status == "PENDING",
            Shop.is_archived == False,
            ShopProfile.is_archived == False,
        )
    )

    # Super admin sees all, field admin sees only their mandla
    if admin.user_type.lower() == "admin" and admin.mandla_id:
         query = query.filter(ShopProfile.mandla_id == admin.mandla_id)

    shops = query.order_by(Shop.created_at.asc()).all()

    return [
        {
            "shop_id": s.id,
            "shop_profile_id": s.shop_profile_id,
            "user_id": s.user_id,
            "business_name": s.profile.business_name,
            "category": s.profile.category,
            "mandla_id": s.profile.mandla_id,
            "created_at": s.created_at,
        }
        for s in shops
    ]


@router.post("/{shop_id}/approve", response_model=None)
def approve_shop(
    shop_id: int,
    admin: User = Depends(require_shop_admin),
    db: Session = Depends(get_db),
    request: Request = None,  
):
    shop = (
        db.query(Shop)
        .filter(
            Shop.id == shop_id,
            Shop.is_archived == False,
        )
        .first()
    )

    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
        
    # Area check for field admin
    if admin.user_type.lower() == "admin" and admin.mandla_id and shop.profile.mandla_id != admin.mandla_id:
        raise HTTPException(status_code=403, detail="You do not have permission to approve shops in this area.")

    if shop.approval_status == "APPROVED":
        raise HTTPException(status_code=400, detail="Shop already approved")

    try:
        shop.approval_status = "APPROVED"
        shop.public_visible = True
        shop.approved_at = datetime.utcnow()
        shop.approved_by = admin.id

        LedgerService.get_or_create_wallet(
            db=db,
            user_id=shop.user_id,
        )

        db.commit()
        db.refresh(shop)

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Shop approval failed: {str(e)}",
        )

    ip_address = None
    if request and request.client:
        ip_address = request.client.host

    log_admin_action(
        db=db,
        admin_id=admin.id,
        module="admin_shop",
        action="APPROVE_SHOP",
        target_id=str(shop.id),
        ip_address=ip_address,
    )

    return {
        "message": "Shop approved successfully",
        "shop_id": shop.id,
    }


@router.post("/{shop_id}/reject", response_model=None)
def reject_shop(
    shop_id: int,
    reason: str = Body(...),
    admin: User = Depends(require_shop_admin),
    db: Session = Depends(get_db),
):
    shop = (
        db.query(Shop)
        .filter(
            Shop.id == shop_id,
            Shop.is_archived == False,
        )
        .first()
    )

    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Area check for field admin
    if admin.user_type.lower() == "admin" and admin.mandla_id and shop.profile.mandla_id != admin.mandla_id:
        raise HTTPException(status_code=403, detail="You do not have permission to reject shops in this area.")
        
    if shop.approval_status == "APPROVED":
        raise HTTPException(status_code=400, detail="Approved shop cannot be rejected")

    shop.approval_status = "REJECTED"
    shop.public_visible = False
    shop.rejected_at = datetime.utcnow()
    shop.rejected_by = admin.id
    shop.rejection_reason = reason

    db.commit()

    return {
        "message": "Shop rejected successfully",
        "shop_id": shop.id,
        "reason": reason,
    }
