"""
app/core/database.py

SQLAlchemy engine, session factory, and Base.

Behaviour differences by database type:
  SQLite  — check_same_thread=False, WAL + NORMAL sync pragmas
  Others  — pool_pre_ping=True, configurable pool size

Use get_db() as a FastAPI dependency to obtain a session per request.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# ─────────────────────────────────────────────────────────────────────────────
# ENGINE
# ─────────────────────────────────────────────────────────────────────────────

_engine_kwargs: dict = {
    "echo": settings.DEBUG,   # logs all SQL in DEBUG mode only
    "future": True,
}

if settings.is_sqlite:
    # SQLite: disable the same-thread check (FastAPI uses a thread pool)
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL / MySQL: connection health-check and pool tuning
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20
    _engine_kwargs["pool_timeout"] = 30
    _engine_kwargs["pool_recycle"] = 1800  # recycle connections every 30 min

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)

# SQLite-specific PRAGMAs for write performance and crash safety.
# WAL mode allows concurrent reads alongside a single write.
if settings.is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")  # enforce FK constraints
        cursor.close()

# ─────────────────────────────────────────────────────────────────────────────
# SESSION
# ─────────────────────────────────────────────────────────────────────────────

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ─────────────────────────────────────────────────────────────────────────────
# DECLARATIVE BASE
# ─────────────────────────────────────────────────────────────────────────────

from app.models.base import Base

# ─────────────────────────────────────────────────────────────────────────────
# REQUEST-SCOPED SESSION DEPENDENCY
# ─────────────────────────────────────────────────────────────────────────────

def get_db() -> Session:
    """
    FastAPI dependency that yields a DB session for the lifetime of one request.
    Always closes the session — even on unhandled exceptions.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
