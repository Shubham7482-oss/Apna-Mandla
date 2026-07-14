"""
app/database.py

Legacy compatibility shim.

All new code should import from app.core.database directly:
    from app.core.database import engine, SessionLocal, get_db, Base

This file exists only to avoid breaking any legacy imports.
"""

from app.core.database import Base, SessionLocal, engine, get_db  # noqa: F401

__all__ = ["engine", "SessionLocal", "Base", "get_db"]
