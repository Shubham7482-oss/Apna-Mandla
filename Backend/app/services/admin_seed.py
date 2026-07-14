# app/services/admin_seed.py

from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.models.admin import AdminUser

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def seed_super_admin(db: Session):
    existing = db.query(AdminUser).filter(
        AdminUser.is_super_admin == True
    ).first()

    if existing:
        print("Super admin already exists.")
        return

    super_admin = AdminUser(
        name="Root Admin",
        phone="9999999999",
        email="root@apnamandla.com",
        hashed_password=hash_password("StrongPass123"),
        is_super_admin=True,
        is_active=True
    )

    db.add(super_admin)
    db.commit()

    print("Super admin created successfully.")