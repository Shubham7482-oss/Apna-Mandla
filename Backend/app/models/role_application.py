import sqlalchemy as sa
from sqlalchemy.orm import relationship

from app.models.base import Base

class RoleApplication(Base):
    __tablename__ = 'role_applications'

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    user_id = sa.Column(sa.Integer, sa.ForeignKey('users.id'), nullable=False)
    requested_role = sa.Column(sa.String, nullable=False)  # e.g., 'SELLER', 'RIDER'
    status = sa.Column(sa.String, nullable=False, default='PENDING') # PENDING, APPROVED, REJECTED
    created_at = sa.Column(sa.DateTime, default=sa.func.now())
    details = sa.Column(sa.JSON, nullable=True) # For any extra info like shop name

    user = relationship("User")
