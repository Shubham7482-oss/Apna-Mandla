from app.core.auth import require_roles
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.rbac import require_roles
from app.models.order import Order
from app.models.shop import Shop
from app.models.user import User

router = APIRouter(prefix="/admin/stats", tags=["Admin Dashboard"])

@router.get("/summary", dependencies=[Depends(require_roles(["admin"]))])
def get_admin_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Admin ke liye poore bazaar ka hisab (Last 24 Hours)"""
    
    # 1. Total Orders & Sales (Lifetime)
    total_orders = db.query(func.count(Order.id)).scalar()
    total_sales = db.query(func.sum(Order.total_amount)).scalar() or 0

    # 2. Orders by Status (Dashboard Charts ke liye)
    status_counts = db.query(Order.status, func.count(Order.id)).group_by(Order.status).all()
    status_map = {status: count for status, count in status_counts}

    # 3. Active Shops & Riders
    active_shops = db.query(Shop).filter(Shop.approval_status == "APPROVED").count()
    pending_shops = db.query(Shop).filter(Shop.approval_status == "PENDING").count()

    # 4. Today's Performance (Mandla Special)
    today = datetime.now().date()
    today_orders = db.query(Order).filter(func.date(Order.created_at) == today).count()
    today_earnings = db.query(func.sum(Order.total_amount)).filter(func.date(Order.created_at) == today).scalar() or 0

    # 5. Commission Calculation (Maan lo aapka 5% commission hai)
    platform_commission = float(total_sales) * 0.05

    return {
        "overview": {
            "total_sales": float(total_sales),
            "platform_commission": platform_commission,
            "total_orders": total_orders,
            "today_orders": today_orders,
            "today_earnings": float(today_earnings)
        },
        "shop_stats": {
            "active": active_shops,
            "pending_approvals": pending_shops
        },
        "order_status_breakdown": status_map
    }

@router.get("/top-shops", dependencies=[Depends(require_roles(["admin"]))])
def get_top_shops(db: Session = Depends(get_db)):
    """Kaunsi dukan sabse zyada kama rahi hai?"""
    top_shops = db.query(
        Shop.id, 
        func.count(Order.id).label("order_count")
    ).join(Order).group_by(Shop.id).order_by(func.count(Order.id).desc()).limit(5).all()
    
    return top_shops
