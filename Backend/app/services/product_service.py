from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from decimal import Decimal

from app.models.product import Product
from app.models.discount import Discount
from app.schemas.product import ProductCreate

class ProductService:

    # 🔒 CREATE PRODUCT (Clean & Updated)
    @staticmethod
    def create_product(db: Session, data: ProductCreate):
        # Note: Limit checks now happen in the Route for better control
        
        new_product = Product(
            shop_id=data.shop_id,
            name=data.name,
            description=data.description,
            price=data.price,
            discount_price=data.discount_price, # Direct field support
            unit=data.unit,
            stock_quantity=data.stock_quantity,
            category_id=data.category_id,
            is_available=data.is_available
        )

        db.add(new_product)
        db.commit()
        db.refresh(new_product)
        return new_product


    # 🚀 HIGH PERFORMANCE — LIST PRODUCTS
    @staticmethod
    def list_products_by_shop(db: Session, shop_id: int):
        # Use joinedload to fetch discounts in ONE single query (Optimization)
        products = db.query(Product).filter(
            Product.shop_id == shop_id,
            Product.is_archived == False
        ).all()

        result = []
        for product in products:
            # Humne model mein property banayi thi 'current_price'
            # Usi ko use karenge logic clean rakhne ke liye
            
            result.append({
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "unit": product.unit,
                "original_price": product.price,
                "discount_price": product.discount_price,
                "final_price": product.discount_price if product.discount_price else product.price,
                "stock": product.stock_quantity,
                "is_available": product.is_available,
                "category_id": product.category_id
            })

        return result