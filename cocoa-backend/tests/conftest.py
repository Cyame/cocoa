"""Pytest fixtures for the Cocoa backend test suite."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import Base

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/cocoa_dev"


@pytest_asyncio.fixture(autouse=True, scope="function")
async def _setup_db():
    """Create and tear down database schema for each test function."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
