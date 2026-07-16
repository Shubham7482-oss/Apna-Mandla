import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

def init_db() -> None:
    """
    Database schema initialization is managed exclusively by Alembic.

    Run `alembic upgrade head` as part of deployment before starting the
    application instead of creating tables from SQLAlchemy metadata at runtime.
    """
    logger.info("Database schema managed by Alembic migrations; skipping runtime table creation.")

def init_db_with_session(db: Session) -> None:
    """
    Reserved for controlled system bootstrap.
    """
    pass
