"""Pytest fixtures for the Cocoa backend test suite.

Isolation model: a session-scoped template database is built once via Alembic
migrations. Every DB-touching test clones a private database from that
template (`CREATE DATABASE ... TEMPLATE ...`), runs against it, and drops it
afterwards. Tests can never see each other's data, and `cocoa_dev` (the
Alembic-managed development schema) is never touched by the test suite.
"""

import os
import subprocess
import uuid

import asyncpg
import pytest_asyncio
from _pytest.monkeypatch import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

_ADMIN_DSN = "postgresql://postgres:postgres@localhost:5432/postgres"
_TEMPLATE_DB = "cocoa_test_template"
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _url(db: str) -> str:
    return f"postgresql+asyncpg://postgres:postgres@localhost:5432/{db}"


async def _exec_admin(sql: str) -> None:
    """Run a statement against the admin database (autocommit, no transaction)."""
    conn = await asyncpg.connect(_ADMIN_DSN)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _template_db():
    """Build the migrated schema template once per test session."""
    await _exec_admin(f'DROP DATABASE IF EXISTS {_TEMPLATE_DB} WITH (FORCE)')
    await _exec_admin(f'CREATE DATABASE {_TEMPLATE_DB}')
    env = {**os.environ, "DATABASE_URL": _url(_TEMPLATE_DB)}
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
    )
    yield _TEMPLATE_DB
    await _exec_admin(f'DROP DATABASE IF EXISTS {_TEMPLATE_DB} WITH (FORCE)')


@pytest_asyncio.fixture
async def db_url(_template_db):
    """A private database cloned from the migrated template, per test."""
    name = f"cocoa_test_{uuid.uuid4().hex[:12]}"
    await _exec_admin(f'CREATE DATABASE {name} TEMPLATE {_template_db}')
    yield _url(name)
    await _exec_admin(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')


@pytest_asyncio.fixture
async def session(db_url):
    """Async ORM session bound to the test's private database."""
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_url: str):
    """TestClient wired to the per-test cloned database."""
    import app.core.db as db_mod
    from app.main import app

    monkeypatch = MonkeyPatch()
    monkeypatch.setattr("app.core.config.settings.DATABASE_URL", db_url)
    db_mod._engine = None
    db_mod._session_factory = None
    with TestClient(app) as tc:
        yield tc
    # Teardown: dispose engine if it was created (lifespan in P3 is stub, no DB — but for P3.5 compatibility)
    if db_mod._engine is not None:
        try:
            await db_mod._engine.dispose()
        except Exception:
            pass  # cross-loop disposal may fail; DROP DATABASE WITH (FORCE) is the backstop
    db_mod._engine = None
    db_mod._session_factory = None
    monkeypatch.undo()
