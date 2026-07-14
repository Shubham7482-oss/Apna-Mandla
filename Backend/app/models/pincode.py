from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, SoftArchiveMixin


class Pincode(Base, TimestampMixin, SoftArchiveMixin):
    """
    First-class Pincode model.

    Each pincode is mapped to a Mandla (city/area) and can be enabled/disabled
    for service. This is the canonical source of truth for area-based access.
    """

    __tablename__ = "pincodes"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String(10), unique=True, nullable=False, index=True)

    mandla_id = Column(
        Integer,
        ForeignKey("mandlas.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    label = Column(String(100), nullable=True)

    # SoftArchiveMixin already provides is_active / is_archived, but we keep a
    # simple flag for service availability semantics.
    is_serviceable = Column(Boolean, default=True, nullable=False)

    mandla = relationship("Mandla", back_populates="pincodes")

