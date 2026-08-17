"""SQLAlchemy async engine, session factory, and declarative base for Eyot."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

_engine = None
_session_factory = None


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_engine():
    """Return the async engine, creating it lazily on first call."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory, creating it lazily on first call."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory
