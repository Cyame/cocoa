"""Alembic migration environment.

Async-aware. Reads ``DATABASE_URL`` from :mod:`app.core.config` and
targets :class:`app.core.db.Base` so that any future
``app/models/*.py`` table is picked up by autogenerate.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Make ``app`` importable when alembic is invoked from the project root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.models.blackboard  # noqa: E402, F401
import app.models.employee  # noqa: E402, F401
import app.models.event  # noqa: E402, F401
import app.models.instance  # noqa: E402, F401
import app.models.memory  # noqa: E402, F401
import app.models.office  # noqa: E402, F401

# Import all model modules so Base.metadata reflects every table.
import app.models.user  # noqa: E402, F401
from app.core.config import settings  # noqa: E402
from app.core.db import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the placeholder url from alembic.ini with the real one.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations against an async engine."""
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations using an async engine wrapped in asyncio.run."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
