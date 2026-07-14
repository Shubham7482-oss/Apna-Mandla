from typing import Optional

from sqlalchemy.orm import Session

from app.models.admin import AdminAuditLog


def log_admin_action(
    db: Session,
    admin_id: Optional[int],
    module: str,
    action: str,
    target_id: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Persist an admin audit log entry.
    """
    entry = AdminAuditLog(
        admin_id=admin_id,
        module=module,
        action=action,
        target_id=target_id,
        ip_address=ip_address,
    )
    db.add(entry)
    db.flush()

