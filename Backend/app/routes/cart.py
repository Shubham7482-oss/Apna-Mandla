from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.cart import Cart, CartItem
from app.models.product import Product

router = APIRouter(prefix="/cart", tags=["Cart"])

@router.post("/add")
def add_to_cart(product_id: int, quantity: int = 1, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    # 1. Product check karein
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product: raise HTTPException(404, "Product nahi mila")

    # 2. User ki Cart dhundo ya banao
    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if not cart:
        cart = Cart(user_id=current_user.id, shop_id=product.shop_id)
        db.add(cart)
        db.flush() # ID generate karne ke liye

    # 3. 🚨 SINGLE SHOP CHECK
    if cart.shop_id != product.shop_id:
        # Agar user dusri dukan se saaman dal raha hai
        # Hum ya toh error denge ya cart khali kar denge
        raise HTTPException(
            status_code=400, 
            detail="Aap ek saath sirf ek hi dukan se order kar sakte hain. Purani cart khali karein?"
        )

    # 4. Item add ya quantity update
    item = db.query(CartItem).filter(CartItem.cart_id == cart.id, CartItem.product_id == product_id).first()
    if item:
        item.quantity += quantity
    else:
        item = CartItem(cart_id=cart.id, product_id=product_id, quantity=quantity)
        db.add(item)

    db.commit()
    return {"message": "Saaman tokri mein daal diya gaya hai"}

@router.get("/")
def get_cart(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if not cart or not cart.items:
        return {"items": [], "total_price": 0}

    # Total Price calculation
    total = sum(item.product.current_price * item.quantity for item in cart.items)
    
    return {
        "shop_id": cart.shop_id,
        "items": [
            {
                "product_id": i.product_id,
                "name": i.product.name,
                "quantity": i.quantity,
                "price": i.product.current_price,
                "subtotal": i.product.current_price * i.quantity
            } for i in cart.items
        ],
        "total_price": total
    }