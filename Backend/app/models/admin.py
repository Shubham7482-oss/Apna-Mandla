# app/models/admin.py

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint
)
from app.models.custom_types import GUID
from sqlalchemy.orm import relationship

# ✅ FIXED IMPORT
from app.models.base import Base


# =========================================================
# ADMIN USER
# =========================================================

class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    name = Column(String(100), nullable=False)
    phone = Column(String(15), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=True)

    hashed_password = Column(String(255), nullable=False)

    is_active = Column(Boolean, default=True)
    is_super_admin = Column(Boolean, default=False)

    role_id = Column(GUID(), ForeignKey("admin_roles.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    role = relationship("AdminRole", back_populates="admins")
    audit_logs = relationship("AdminAuditLog", back_populates="admin")


# =========================================================
# ADMIN ROLE
# =========================================================

class AdminRole(Base):
    __tablename__ = "admin_roles"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    admins = relationship("AdminUser", back_populates="role")
    permissions = relationship("AdminRolePermission", back_populates="role")


# =========================================================
# ADMIN PERMISSION
# =========================================================

class AdminPermission(Base):
    __tablename__ = "admin_permissions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    module = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("module", "action", name="unique_module_action"),
    )


# =========================================================
# ROLE ↔ PERMISSION MAPPING
# =========================================================

class AdminRolePermission(Base):
    __tablename__ = "admin_role_permissions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    role_id = Column(GUID(), ForeignKey("admin_roles.id", ondelete="CASCADE"))
    permission_id = Column(GUID(), ForeignKey("admin_permissions.id", ondelete="CASCADE"))

    created_at = Column(DateTime, default=datetime.utcnow)

    role = relationship("AdminRole", back_populates="permissions")
    permission = relationship("AdminPermission")


# =========================================================
# ADMIN AUDIT LOG
# =========================================================

class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    admin_id = Column(
        GUID(),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        index=True,
    )

    module = Column(String(100), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    target_id = Column(String(100), nullable=True)

    ip_address = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    admin = relationship("AdminUser", back_populates="audit_logs")