# app/core/__init__.py

"""
Core module initializer for Apna Mandla backend.

This package contains:
- configuration management
- database setup
- security primitives
- system-level initialization logic

Do NOT place business logic here.
"""

from app.core.config import settings
from app.core.database import engine, SessionLocal
