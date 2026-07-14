
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum

from app.models.base import Base, TimestampMixin

# ================================================
# 🔹 NOTIFICATION MODEL & ENUMS
# ================================================

class NotificationType(str, enum.Enum):
    ORDER_STATUS = "ORDER_STATUS"
    UDHAR_REMINDER = "UDHAR_REMINDER"
    PROMOTION = "PROMOTION"
    WALLET_TRANSACTION = "WALLET_TRANSACTION"
    GENERAL = "GENERAL"


class Notification(Base, TimestampMixin):
    """
    Main Notification Table - Stores the content of each notification.
    """

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    
    # Content
    title = Column(String(100), nullable=False)
    body = Column(Text, nullable=False)
    
    # Type & Metadata
    notification_type = Column(SAEnum(NotificationType), nullable=False, default=NotificationType.GENERAL)
    related_entity_id = Column(String(50), nullable=True) # e.g., Order ID, Udhar ID
    image_url = Column(String(255), nullable=True)
    
    # Scheduling (for future use)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)


class UserNotification(Base, TimestampMixin):
    """
    Tracks which user has received which notification and if they have read it.
    """

    __tablename__ = "user_notifications"

    id = Column(Integer, primary_key=True, index=True)
    
    # Links
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, index=True)

    # Status
    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="notifications")
    notification = relationship("Notification")

