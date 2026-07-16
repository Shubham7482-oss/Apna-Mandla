import logging
from sqlalchemy.orm import Session

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
    Schema changes are managed exclusively by Alembic migrations.
    """
    # Plain text used to prevent UnicodeEncodeError on Windows
    logger.info("Database schema managed by Alembic migrations.")

def init_db_with_session(db: Session) -> None:
    """
    Reserved for controlled system bootstrap.
    """
    pass
