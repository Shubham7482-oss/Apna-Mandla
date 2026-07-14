from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.core.rbac import require_roles
from app.core.pincode import get_active_pincode
from app.models.mandla import Mandla
from app.models.pincode import Pincode
from app.models.order import Order, OrderStatus, PaymentMode
from app.models.order_item import OrderItem
from app.models.shop import Shop
from app.models.product import Product
from app.models.user import User
from app.models.payment import Payment
from app.models.wallet import Wallet
from app.models.ledger_entry import LedgerEntry
from app.services.discount_service import DiscountEngine
from app.utils.fcm import send_fcm_notification

router = APIRouter(prefix="/orders", tags=["Orders"])


# ───────────────────────────────
# SCHEMAS
# ───────────────────────────────
class ItemRequest(BaseModel):
    product_id: int
    quantity: int


class OrderCreateRequest(BaseModel):
    shop_id: int
    items: List[ItemRequest]
    note: Optional[str] = None
    payment_mode: PaymentMode = PaymentMode.COD
    delivery_address: str
    
class OrderUpdateRequest(BaseModel):
    status: OrderStatus

# ───────────────────────────────
# CREATE ORDER
# ───────────────────────────────
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_order(
    data: OrderCreateRequest,
    current_user: User = Depends(require_roles(["customer"])),
    db: Session = Depends(get_db),
    pincode: Pincode = Depends(get_active_pincode),
):
    if not data.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    shop = db.query(Shop).filter(
        Shop.id == data.shop_id,
        Shop.approval_status == "APPROVED",
        Shop.is_open == True,
    ).first()

    if not shop or not shop.profile:
        raise HTTPException(
            status_code=404,
            detail="Shop not available for orders",
        )

    mandla = db.query(Mandla).filter(
        Mandla.id == shop.profile.mandla_id,
        Mandla.is_active == True,
    ).first()

    if not mandla or mandla.id != pincode.mandla_id:
        raise HTTPException(
            status_code=403,
            detail="Shop does not serve this pincode.",
        )

    # Calculate subtotal and prepare items for discount engine
    items_for_discount = []
    subtotal = Decimal("0.00")
    
    for item_data in data.items:
        product = db.query(Product).filter(
            Product.id == item_data.product_id,
            Product.shop_id == data.shop_id,
            Product.is_archived == False
        ).first()

        if not product:
            raise HTTPException(400, f"Product {item_data.product_id} not found")

        if not product.is_available:
            raise HTTPException(400, f"{product.name} is out of stock")

        if product.manage_stock and product.stock_quantity < item_data.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {product.name}"
            )

        price = (
            Decimal(str(product.discount_price))
            if product.discount_price and product.discount_price > 0
            else Decimal(str(product.price))
        )

        subtotal += price * item_data.quantity
        
        items_for_discount.append({
            "product_id": product.id,
            "quantity": item_data.quantity,
            "price": float(price),
            "product_obj": product # Keep reference to update stock later
        })

    if subtotal <= 0:
        raise HTTPException(400, "Order total cannot be zero")

    # 🔥 APPLY DISCOUNT ENGINE
    discount_val = DiscountEngine.calculate_order_discount(
        db, 
        shop.owner, 
        items_for_discount, 
        float(subtotal)
    )
    discount_amount = Decimal(str(discount_val))

    order_status = (
        OrderStatus.PAYMENT_PENDING
        if data.payment_mode == PaymentMode.PREPAID
        else OrderStatus.CREATED
    )

    delivery_fee = Decimal("20.00")
    total_amount = subtotal - discount_amount + delivery_fee

    new_order = Order(
        customer_id=current_user.id,
        shop_id=shop.id,
        mandla_id=shop.profile.mandla_id,
        status=order_status,
        payment_mode=data.payment_mode,
        note=data.note,
        subtotal=subtotal,
        discount_amount=discount_amount,
        delivery_fee=delivery_fee,
        total_amount=total_amount,
        delivery_address=data.delivery_address,
    )

    if data.payment_mode == PaymentMode.PREPAID:
        # Fetch customer's wallet
        wallet = db.query(Wallet).filter(Wallet.user_id == current_user.id).with_for_update().first()
        if not wallet or wallet.balance < new_order.total_amount:
            raise HTTPException(status_code=400, detail="Insufficient wallet balance for this prepaid order.")
        
        # Deduct
        wallet.balance -= new_order.total_amount
        db.add(LedgerEntry(
            wallet_id=wallet.id,
            entry_type="DEBIT",
            amount=new_order.total_amount,
            description=f"Payment for Order #{new_order.id}"
        ))
        
        new_order.status = OrderStatus.CREATED # Set to created as payment is done

    db.add(new_order)
    db.flush()

    # Add OrderItems and update stock
    for item in items_for_discount:
        product = item['product_obj']
        db.add(OrderItem(
            order_id=new_order.id,
            product_id=product.id,
            quantity=item['quantity'],
            price_at_order=Decimal(str(item['price']))
        ))

        if product.manage_stock:
            product.stock_quantity -= item['quantity']

    payment_id = None
    if data.payment_mode == PaymentMode.PREPAID:
        payment = Payment(
            order_id=new_order.id,
            user_id=current_user.id,
            amount=float(total_amount),
            status="SUCCESS"
        )
        db.add(payment)
        db.flush()
        payment_id = payment.id

    db.commit()
    db.refresh(new_order)
    
    # Send notification to shop owner
    if shop.owner.device_token:
        send_fcm_notification(
            device_token=shop.owner.device_token,
            title="New Order Received!",
            body=f"You have a new order #{new_order.id} for Rs. {new_order.total_amount}.",
            data={"order_id": str(new_order.id), "type": "NEW_ORDER"}
        )


    return {
        "order_id": new_order.id,
        "payment_id": payment_id,
        "subtotal": float(new_order.subtotal),
        "discount": float(new_order.discount_amount),
        "total_amount": float(new_order.total_amount),
        "status": new_order.status,
    }

# ───────────────────────────────
# UPDATE ORDER STATUS
# ───────────────────────────────
@router.put("/{order_id}/status", status_code=status.HTTP_200_OK)
def update_order_status(
    order_id: int,
    data: OrderUpdateRequest,
    current_user: User = Depends(require_roles(["shop", "admin"])),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Authorization: Ensure shop owner is updating their own order
    if "shop" in current_user.get_roles() and order.shop.owner.id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this order")

    order.status = data.status
    db.commit()
    db.refresh(order)
    
    # Send notification to customer
    if order.customer.device_token:
        send_fcm_notification(
            device_token=order.customer.device_token,
            title="Order Status Updated",
            body=f"Your order #{order.id} is now {order.status.value}.",
            data={"order_id": str(order.id), "type": "ORDER_STATUS_UPDATE"}
        )

    return {"message": "Order status updated successfully", "new_status": order.status}


# ───────────────────────────────
# CUSTOMER ORDER LIST
# ───────────────────────────────
@router.get("/customer")
def get_customer_orders(
    current_user: User = Depends(require_roles(["customer"])),
    db: Session = Depends(get_db),
):
    orders = db.query(Order).filter(
        Order.customer_id == current_user.id,
        Order.is_archived == False
    ).order_by(Order.id.desc()).all()

    response = []

    for order in orders:
        payment = db.query(Payment).filter(
            Payment.order_id == order.id
        ).first()

        response.append({
            "order_id": order.id,
            "shop_id": order.shop_id,
            "total_amount": float(order.total_amount),
            "status": order.status,
            "payment_mode": order.payment_mode,
            "payment_status": payment.status if payment else None,
            "created_at": order.created_at,
        })

    return response


# ───────────────────────────────
# SINGLE ORDER DETAILS
# ───────────────────────────────
@router.get("/{order_id}")
def get_order_details(
    order_id: int,
    current_user: User = Depends(require_roles(["customer", "shop"])),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # Authorization
    if "customer" in current_user.get_roles() and order.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")
    if "shop" in current_user.get_roles() and order.shop.owner.id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")


    payment = db.query(Payment).filter(
        Payment.order_id == order.id
    ).first()

    items = db.query(OrderItem).filter(
        OrderItem.order_id == order.id
    ).all()

    return {
        "order_id": order.id,
        "shop_id": order.shop_id,
        "subtotal": float(order.subtotal),
        "discount": float(order.discount_amount),
        "delivery_fee": float(order.delivery_fee),
        "total_amount": float(order.total_amount),
        "status": order.status,
        "payment_mode": order.payment_mode,
        "payment_status": payment.status if payment else None,
        "items": [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price": float(item.price_at_order),
            }
            for item in items
        ],
        "created_at": order.created_at,
    }