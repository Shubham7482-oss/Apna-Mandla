from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models.commission import CommissionConfig


# ─────────────────────────────────────────────
# GET ACTIVE COMMISSION (NO COMMIT)
# ─────────────────────────────────────────────
def get_active_commission_percent(db: Session) -> Decimal:
    """
    Returns active commission percentage.

    Rules:
    - Only one active config should exist.
    - If multiple active exist → latest one used.
    - If none exist → safe fallback error.
    """

    try:
        stmt = (
            select(CommissionConfig)
            .where(CommissionConfig.is_active == True)
            .order_by(CommissionConfig.id.desc())
            .limit(1)
        )

        config = db.execute(stmt).scalar_one_or_none()

        if not config:
            raise ValueError("No active commission configuration found")

        percent = Decimal(str(config.percent))

        # Basic sanity check
        if percent < 0 or percent > 100:
            raise ValueError("Invalid commission percent configured")

        return percent

    except SQLAlchemyError as e:
        raise e