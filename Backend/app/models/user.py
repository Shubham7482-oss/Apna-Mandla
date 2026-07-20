from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin, SoftArchiveMixin
from app.models.active_session import ActiveSession


class User(Base, TimestampMixin, SoftArchiveMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(15), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=True)
    unique_id = Column(String(50), unique=True, index=True)
    image_url = Column(String(255), nullable=True)
    device_token = Column(String(255), nullable=True)

    user_type = Column(String(20), default="CUSTOMER")  # CUSTOMER, SELLER, RIDER, ADMIN, SUPER_ADMIN
    admin_role = Column(String(30), nullable=True)

    signup_ip = Column(String(45), nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    phone_verified = Column(Boolean, default=False, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    mandla_id = Column(Integer, ForeignKey("mandlas.id"), nullable=True)

    @property
    def password_hash(self) -> str:
        return self.hashed_password

    @password_hash.setter
    def password_hash(self, value: str) -> None:
        self.hashed_password = value

    # Core Relationships only
    mandla = relationship("Mandla", back_populates="users")
    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")
    shop_profile = relationship("ShopProfile", back_populates="user", uselist=False)
    rider_profile = relationship("RiderProfile", back_populates="user", uselist=False)
    customer_profile = relationship("CustomerProfile", back_populates="user", uselist=False)
    mini_website = relationship("MiniWebsite", back_populates="user", uselist=False)
    sessions = relationship("ActiveSession", back_populates="user", cascade="all, delete-orphan")
    tokens = relationship("Token", back_populates="user", cascade="all, delete-orphan")

    # FIXED
    udhar_accounts = relationship(
        "UdharAccount",
        foreign_keys="UdharAccount.borrower_id",
        back_populates="borrower",
    )
