from app.core.database import get_db
from app.core.auth import require_roles
from app.models.user import User
# app/routes/admin_permission.py

from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session

from app.models.admin import AdminRolePermission, AdminPermission


def require_permission(module: str, action: str):
    def permission_checker(
        current_admin = Depends(require_roles(["admin"])),
        db: Session = Depends(get_db)
    ):
        # Super admin bypass
        if current_admin.is_super_admin:
            return current_admin

        # Find permission
        permission = db.query(AdminPermission).filter(
            AdminPermission.module == module,
            AdminPermission.action == action
        ).first()

        if not permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission not defined"
            )

        # Check role permission mapping
        role_permission = db.query(AdminRolePermission).filter(
            AdminRolePermission.role_id == current_admin.role_id,
            AdminRolePermission.permission_id == permission.id
        ).first()

        if not role_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )

        return current_admin

    return permission_checker