from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, SoftArchiveMixin


class Mandla(Base, TimestampMixin, SoftArchiveMixin):
    """
    Mandla = City / Area / Local Region
    """

    __tablename__ = "mandlas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    state = Column(String(100), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    # ✅ use back_populates (NOT backref)
    users = relationship(
        "User",
        back_populates="mandla",
    )

    shops = relationship(
        "ShopProfile",
        back_populates="mandla",
    )

    pincodes = relationship(
        "Pincode",
        back_populates="mandla",
        cascade="all, delete-orphan",
    )