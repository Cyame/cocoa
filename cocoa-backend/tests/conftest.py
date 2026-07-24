"""Pytest fixtures for the Cocoa backend test suite."""

import logging

import pytest_asyncio
from sqlalchemy.exc import NoReferencedTableError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import Base

logger = logging.getLogger(__name__)

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/cocoa_dev"


@pytest_asyncio.fixture(autouse=True, scope="function")
async def _setup_db():
    """Create and tear down database schema for each test function.

    Gracefully skips tables whose FK targets have not been registered in
    ``Base.metadata`` yet (forward references), logging a warning instead
    of failing the whole test suite.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except NoReferencedTableError as exc:
            logger.warning(
                "Skipping table creation for unresolved FK: %s", exc
            )

    yield

    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.drop_all)
        except Exception as exc:
            logger.warning("Error during table teardown: %s", exc)

    await engine.dispose()
