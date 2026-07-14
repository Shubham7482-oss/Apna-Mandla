from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.rbac import require_roles
from app.core.database import get_db
from app.models.discount import DiscountRule
from app.models.order import Order, OrderStatus
from app.models.payment import Payment
from app.models.rider import Rider
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.models.user import User
from app.models.product import Product


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _as_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@router.get("/admin")
def admin_dashboard(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(["ADMIN", "SUPER_ADMIN"])),
):
    total_users = db.query(func.count(User.id)).scalar() or 0

    total_sellers = (
        db.query(func.count(Shop.id))
        .filter(Shop.is_archived == False)  # noqa: E712
        .scalar()
        or 0
    )

    total_orders = (
        db.query(func.count(Order.id))
        .filter(Order.is_archived == False)  # noqa: E712
        .scalar()
        or 0
    )

    total_revenue_value = (
        db.query(func.coalesce(func.sum(Order.total_amount), 0))
        .filter(Order.is_archived == False)  # noqa: E712
        .scalar()
    )
    total_revenue = _as_float(total_revenue_value)

    now = datetime.utcnow()
    active_subscriptions = (
        db.query(func.count(Subscription.id))
        .filter(
            Subscription.status == "ACTIVE",
            Subscription.end_date > now,
        )
        .scalar()
        or 0
    )

    recent_orders = (
        db.query(Order)
        .filter(Order.is_archived == False)  # noqa: E712
        .order_by(Order.created_at.desc())
        .limit(10)
        .all()
    )

    recent_orders_data = []
    for o in recent_orders:
        recent_orders_data.append(
            {
                "order_id": o.id,
                "status": o.status.value if isinstance(o.status, OrderStatus) else str(o.status),
                "total_amount": _as_float(o.total_amount),
                "created_at": o.created_at,
                "shop_id": o.shop_id,
                "customer_id": o.customer_id,
            }
        )

    pending_sellers = (
        db.query(Shop)
        .filter(
            Shop.approval_status == "PENDING",
            Shop.is_archived == False,  # noqa: E712
        )
        .order_by(Shop.created_at.desc())
        .limit(10)
        .all()
    )

    pending_sellers_data = []
    for s in pending_sellers:
        profile = s.profile
        pending_sellers_data.append(
            {
                "shop_id": s.id,
                "business_name": getattr(profile, "business_name", None),
                "category": getattr(profile, "category", None),
                "approval_status": s.approval_status,
                "created_at": s.created_at,
            }
        )

    commission_rate = 0.1
    commission_overview = {
        "commission_rate": commission_rate,
        "estimated_total_commission": round(total_revenue * commission_rate, 2),
    }

    return {
        "admin_info": {
            "user_type": current_admin.user_type,
            "admin_role": getattr(current_admin, "admin_role", None)
        },
        "total_users": total_users,
        "total_sellers": total_sellers,
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "active_subscriptions": active_subscriptions,
        "recent_orders": recent_orders_data,
        "pending_sellers": pending_sellers_data,
        "commission_overview": commission_overview,
    }


@router.get("/seller")
def seller_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["SHOP"])),
):
    shop = (
        db.query(Shop)
        .filter(
            Shop.user_id == current_user.id,
            Shop.is_archived == False,  # noqa: E712
        )
        .first()
    )

    if not shop:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shop profile not found for current user",
        )

    # Calculate Total Revenue from all orders for the shop
    total_revenue_value = (
        db.query(func.coalesce(func.sum(Order.total_amount), 0))
        .filter(
            Order.shop_id == shop.id,
            Order.is_archived == False,  # noqa: E712
        )
        .scalar()
    )
    total_revenue = _as_float(total_revenue_value)

    # Calculate Total Orders (All Time) for the shop
    total_orders = (
        db.query(func.count(Order.id))
        .filter(
            Order.shop_id == shop.id,
            Order.is_archived == False,  # noqa: E712
        )
        .scalar() or 0
    )

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    today_orders = (
        db.query(func.count(Order.id))
        .filter(
            Order.shop_id == shop.id,
            Order.created_at >= today_start,
            Order.is_archived == False,  # noqa: E712
        )
        .scalar()
        or 0
    )

    total_products = (
        db.query(func.count(Product.id))
        .filter(
            Product.shop_id == shop.id,
            Product.is_archived == False,  # noqa: E712
        )
        .scalar()
        or 0
    )

    pending_statuses = [
        OrderStatus.CREATED,
        OrderStatus.SHOP_ACCEPTED,
        OrderStatus.READY_FOR_PICKUP,
        OrderStatus.BROADCASTING,
        OrderStatus.RIDER_ASSIGNED,
        OrderStatus.OUT_FOR_DELIVERY,
    ]

    pending_orders = (
        db.query(func.count(Order.id))
        .filter(
            Order.shop_id == shop.id,
            Order.status.in_(pending_statuses),
            Order.is_archived == False,  # noqa: E712
        )
        .scalar()
        or 0
    )

    # This represents received payments, which might be different from total revenue
    earnings_total_value = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .join(Order, Payment.order_id == Order.id)
        .filter(
            Order.shop_id == shop.id,
            Payment.status == "SUCCESS",
            Payment.is_archived == False,  # noqa: E712
        )
        .scalar()
    )
    earnings_total = _as_float(earnings_total_value)

    low_stock_products = (
        db.query(Product)
        .filter(
            Product.shop_id == shop.id,
            Product.manage_stock == True,  # noqa: E712
            Product.stock_quantity <= 5,
            Product.is_archived == False,  # noqa: E712
        )
        .order_by(Product.stock_quantity.asc())
        .limit(10)
        .all()
    )

    low_stock_data = [
        {
            "product_id": p.id,
            "name": p.name,
            "stock_quantity": p.stock_quantity,
        }
        for p in low_stock_products
    ]

    recent_orders = (
        db.query(Order)
        .filter(
            Order.shop_id == shop.id,
            Order.is_archived == False,  # noqa: E712
        )
        .order_by(Order.created_at.desc())
        .limit(10)
        .all()
    )

    recent_orders_data = []
    for o in recent_orders:
        recent_orders_data.append(
            {
                "order_id": o.id,
                "status": o.status.value if isinstance(o.status, OrderStatus) else str(o.status),
                "total_amount": _as_float(o.total_amount),
                "created_at": o.created_at,
            }
        )

    rating = None
    if shop.profile is not None:
        rating = getattr(shop.profile, "rating", None)

    return {
        "shop": {
            "id": shop.id,
            "name": getattr(shop.profile, "business_name", None) if shop.profile else None,
            "category": getattr(shop.profile, "category", None) if shop.profile else None,
            "is_open": shop.is_open,
        },
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "today_orders": today_orders,
        "total_products": total_products,
        "pending_orders": pending_orders,
        "earnings_total": earnings_total,
        "low_stock": low_stock_data,
        "recent_orders": recent_orders_data,
        "rating": rating,
    }


@router.get("/customer")
def customer_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["CUSTOMER"])),
):
    active_statuses = [
        OrderStatus.CREATED,
        OrderStatus.SHOP_ACCEPTED,
        OrderStatus.READY_FOR_PICKUP,
        OrderStatus.BROADCASTING,
        OrderStatus.RIDER_ASSIGNED,
        OrderStatus.OUT_FOR_DELIVERY,
    ]

    active_orders = (
        db.query(func.count(Order.id))
        .filter(
            Order.customer_id == current_user.id,
            Order.status.in_(active_statuses),
            Order.is_archived == False,  # noqa: E712
        )
        .scalar()
        or 0
    )

    recent_orders = (
        db.query(Order)
        .filter(
            Order.customer_id == current_user.id,
            Order.is_archived == False,  # noqa: E712
        )
        .order_by(Order.created_at.desc())
        .limit(10)
        .all()
    )

    recent_orders_data = []
    for o in recent_orders:
        recent_orders_data.append(
            {
                "order_id": o.id,
                "status": o.status.value if isinstance(o.status, OrderStatus) else str(o.status),
                "total_amount": _as_float(o.total_amount),
                "created_at": o.created_at,
                "shop_id": o.shop_id,
            }
        )

    # Coupons = active discounts available in system
    total_coupons = (
        db.query(func.count(DiscountRule.id))
        .filter(DiscountRule.is_active == True)  # noqa: E712
        .scalar()
        or 0
    )

    # Saved shops feature is not modelled yet; expose as 0 for now
    saved_shops = 0

    return {
        "active_orders": active_orders,
        "wallet_balance": current_user.wallet_balance,
        "saved_shops": saved_shops,
        "coupons": total_coupons,
        "recent_orders": recent_orders_data,
    }


@router.get("/rider")
def rider_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rider = (
        db.query(Rider)
        .filter(
            Rider.user_id == current_user.id,
            Rider.is_archived == False,  # noqa: E712
        )
        .first()
    )

    if not rider:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rider profile not found for current user",
        )

    # Orders assigned to this rider (via RiderProfile)
    assigned_orders_q = db.query(Order).filter(
        Order.assigned_rider_id == rider.rider_profile_id,
        Order.is_archived == False,  # noqa: E712
    )

    active_statuses = [
        OrderStatus.RIDER_ASSIGNED,
        OrderStatus.OUT_FOR_DELIVERY,
    ]

    assigned_orders = (
        assigned_orders_q.filter(Order.status.in_(active_statuses)).count()
    )

    completed_orders = rider.completed_orders_count

    # Earnings today are not tracked separately; use COD liability as proxy
    earnings_today = _as_float(rider.cod_liability)

    history_orders = (
        assigned_orders_q.order_by(Order.created_at.desc()).limit(15).all()
    )

    history_data = []
    for o in history_orders:
        history_data.append(
            {
                "order_id": o.id,
                "status": o.status.value if isinstance(o.status, OrderStatus) else str(o.status),
                "total_amount": _as_float(o.total_amount),
                "created_at": o.created_at,
            }
        )

    return {
        "assigned_orders": assigned_orders,
        "completed_orders": completed_orders,
        "earnings_today": earnings_today,
        "is_online": rider.on_duty,
        "delivery_history": history_data,
    }
