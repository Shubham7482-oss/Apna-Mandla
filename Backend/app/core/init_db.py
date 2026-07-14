import logging
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models.base import Base

# ───────────────────────────────
# IMPORT ALL MODELS HERE
# ───────────────────────────────

from app.models import (
    user,
    customer_profile,
    rider_profile,
    rider,
    shop_profile,
    shop,
    mini_website,
    order,
    order_item,
    payment,
    otp,
    ad,
    shop_category,
    subscription_plan,
    subscription,
    rating,  
    product,
    wallet,
    ledger_entry,
    udhar_account,
    udhar_transaction,
    notification,
    active_session
)

logger = logging.getLogger(__name__)

def init_db() -> None:
    """
    Initialize database schema.
    Creates tables if they don't exist.
    """
    # Plain text used to prevent UnicodeEncodeError on Windows
    logger.info("Initializing database schema...")

    try:
        # Ye command models ke basis par database mein tables banati hai
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema verified / created successfully.")
    except Exception as e:
        logger.error("Database initialization failed.")
        logger.error(str(e))
        raise

def init_db_with_session(db: Session) -> None:
    """
    Reserved for controlled system bootstrap.
    """
    pass