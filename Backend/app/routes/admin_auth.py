from app.core.database import get_db
from app.core.auth import require_roles
from app.models.user import User
# app/routes/admin_auth.py

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.admin_auth import (
    authenticate_admin,
    create_admin_access_token
)
from app.models.admin import AdminUser


router = APIRouter(prefix="/admin", tags=["Admin"])


# ───────────────────────────────
# DB DEPENDENCY
# ───────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ───────────────────────────────
# LOGIN
# ───────────────────────────────
@router.post("/login")
def admin_login(
    phone: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    admin = authenticate_admin(db, phone, password)

    # 🔐 IMPORTANT — Account must be active
    if not admin.is_active:
        raise HTTPException(
            status_code=403,
            detail="Admin account disabled"
        )

    token = create_admin_access_token(str(admin.id))

    return {
        "access_token": token,
        "token_type": "bearer"
    }


# ───────────────────────────────
# CURRENT ADMIN
# ───────────────────────────────
@router.get("/me")
def admin_me(current_admin = Depends(require_roles(["admin"]))):
    return {
        "id": str(current_admin.id),
        "name": current_admin.name,
        "phone": current_admin.phone,
        "is_super_admin": current_admin.is_super_admin,
        "is_active": current_admin.is_active,
    }