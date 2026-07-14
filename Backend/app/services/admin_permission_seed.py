# app/services/admin_permission_seed.py

from sqlalchemy.orm import Session
from app.models.admin import (
    AdminRole,
    AdminPermission,
    AdminRolePermission,
)

# ===============================
# SEED BASIC ROLE + PERMISSIONS
# ===============================

def seed_basic_permissions(db: Session):

    # 1️⃣ Create Role
    role = db.query(AdminRole).filter(
        AdminRole.name == "Operations Admin"
    ).first()

    if not role:
        role = AdminRole(
            name="Operations Admin",
            description="Handles shop and order approvals"
        )
        db.add(role)
        db.commit()
        db.refresh(role)

    # 2️⃣ Create Permissions
    permissions_data = [
        ("shops", "approve"),
        ("shops", "reject"),
        ("orders", "view"),
        ("orders", "approve"),
    ]

    for module, action in permissions_data:
        permission = db.query(AdminPermission).filter(
            AdminPermission.module == module,
            AdminPermission.action == action
        ).first()

        if not permission:
            permission = AdminPermission(
                module=module,
                action=action
            )
            db.add(permission)
            db.commit()
            db.refresh(permission)

        # 3️⃣ Map role to permission
        mapping = db.query(AdminRolePermission).filter(
            AdminRolePermission.role_id == role.id,
            AdminRolePermission.permission_id == permission.id
        ).first()

        if not mapping:
            mapping = AdminRolePermission(
                role_id=role.id,
                permission_id=permission.id
            )
            db.add(mapping)
            db.commit()

    print("Basic permissions seeded successfully.")