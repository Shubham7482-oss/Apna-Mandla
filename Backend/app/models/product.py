from sqlalchemy import Column, Integer, String, Numeric, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, SoftArchiveMixin


class ProductCategory(Base):
    """
    Simple product category table for grouping products.
    Backed by the `product_categories` table.
    """

    __tablename__ = "product_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)

    # Relationship to products
    products = relationship("Product", back_populates="category")


class Product(Base, TimestampMixin, SoftArchiveMixin):
    """
    Shop Product Entity - Optimized for Apna Mandla v1 Launch.
    """

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    # ───────────────────────────────
    # LINKED ENTITIES
    # ───────────────────────────────
    # Note: Humne "shops" table (Shop model) ko target kiya hai
    shop_id = Column(
        Integer,
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Product Category (e.g., Kirana, Dairy, Vegetables)
    category_id = Column(
        Integer,
        ForeignKey("product_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ───────────────────────────────
    # PRODUCT DETAILS
    # ───────────────────────────────
    name = Column(String(150), nullable=False, index=True)
    description = Column(Text, nullable=True) 
    
    # Unit tracking (e.g., "kg", "packet", "piece")
    unit = Column(String(20), default="piece", nullable=False)

    # ✅ NEW: Product Image (Upload utility se aane wala path yahan save hoga)
    image_url = Column(String(255), nullable=True)

    # ───────────────────────────────
    # FINANCIAL DATA
    # ───────────────────────────────
    # Numeric(10, 2) is perfect for money
    price = Column(Numeric(10, 2), nullable=False)
    discount_price = Column(Numeric(10, 2), nullable=True)

    # ───────────────────────────────
    # INVENTORY & STATUS
    # ───────────────────────────────
    is_available = Column(Boolean, default=True, nullable=False)
    
    # Stock management
    stock_quantity = Column(Integer, default=0, nullable=False)
    manage_stock = Column(Boolean, default=False, nullable=False)

    # ───────────────────────────────
    # RELATIONSHIPS
    # ───────────────────────────────
    shop = relationship("Shop", back_populates="products")
    category = relationship("ProductCategory", back_populates="products")

    # ───────────────────────────────
    # HELPERS
    # ───────────────────────────────
    @property
    def current_price(self):
        """Returns discount price if exists, otherwise normal price"""
        return self.discount_price if self.discount_price and self.discount_price > 0 else self.price

    def __repr__(self):
        return f"<Product {self.name} - ₹{self.current_price}>"