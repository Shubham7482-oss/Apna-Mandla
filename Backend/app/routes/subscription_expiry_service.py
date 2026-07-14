from datetime import datetime
from sqlalchemy.orm import Session
from app.models.subscription import Subscription


def expire_subscriptions(db: Session):

    now = datetime.utcnow()

    subs = db.query(Subscription).filter(
        Subscription.status == "ACTIVE",
        Subscription.end_date < now
    ).all()

    for sub in subs:
        sub.status = "EXPIRED"

    db.commit()