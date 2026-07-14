from sqlalchemy.orm import Session

from app.models.role_application import RoleApplication
from app.schemas.role_application import RoleApplicationCreate


def create_application(db: Session, *, user_id: int, requested_role: str, details: dict = None):
    db_obj = RoleApplication(user_id=user_id, requested_role=requested_role, details=details)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def get_pending_applications(db: Session):
    return db.query(RoleApplication).filter(RoleApplication.status == 'PENDING').all()

def get_application(db: Session, *, application_id: int):
    return db.query(RoleApplication).filter(RoleApplication.id == application_id).first()

def update_application_status(db: Session, *, db_obj: RoleApplication, status: str):
    db_obj.status = status
    db.commit()
    db.refresh(db_obj)
    return db_obj
