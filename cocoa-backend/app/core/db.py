"""SQLAlchemy declarative base for the Cocoa backend.

P0 stub — no models are defined yet. ``alembic/env.py`` imports
``Base`` from this module so future ``app/models/*.py`` tables register
against the same metadata.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
