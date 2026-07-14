from sqlalchemy import Column, Integer, String, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin
import enum

class ComplaintStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"

class Complaint(Base, TimestampMixin):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    subject = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(20), default="OPEN")
    
    admin_note = Column(Text, nullable=True) # Resolved note

    user = relationship("User")
