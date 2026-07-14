# app/services/user_service.py

from sqlalchemy.orm import Session
from datetime import datetime

from app.models.user import User
from app.core.security import get_password_hash


class UserService:
    """
    User service layer.

    Handles:
    - user creation
    - password setup
    - verification flags
    - safe archival

    RULES:
    - No request/response objects
    - DB session must be injected
    """

    @staticmethod
    def create_user(
        db: Session,
        phone_number: str,
        email: str,
        user_type: str,
    ) -> User:
        user = User(
            phone_number=phone_number,
            email=email,
            user_type=user_type,
            phone_verified=False,
            email_verified=False,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def set_password(
        db: Session,
        user: User,
        password: str,
    ) -> None:
        user.password_hash = get_password_hash(password)
        db.commit()

    @staticmethod
    def mark_phone_verified(
        db: Session,
        user: User,
    ) -> None:
        user.phone_verified = True
        db.commit()

    @staticmethod
    def mark_email_verified(
        db: Session,
        user: User,
    ) -> None:
        user.email_verified = True
        db.commit()

    @staticmethod
    def archive_user(
        db: Session,
        user: User,
        reason: str | None = None,
    ) -> None:
        user.is_active = False
        user.is_archived = True
        user.archived_at = datetime.utcnow()
        db.commit()
