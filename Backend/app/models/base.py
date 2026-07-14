from datetime import datetime, timezone
from sqlalchemy import DateTime, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ───────────────────────────────
# MODERN SQLALCHEMY BASE (2.x STYLE)
# ───────────────────────────────

class Base(DeclarativeBase):
    pass


# ───────────────────────────────
# TIMESTAMP MIXIN
# ───────────────────────────────

class TimestampMixin:
    # ✅ FIX: Using timezone-aware DateTime and lambda for true dynamic time
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ───────────────────────────────
# SOFT ARCHIVE MIXIN
# ───────────────────────────────

class SoftArchiveMixin:
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # ✅ FIX: Timezone support for archived records
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )