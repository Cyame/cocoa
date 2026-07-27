"""P11c Todo 12: ``app.main.lifespan`` owns the K8s EventWatcher lifecycle.

Two tests pin the seam:

1. ``test_lifespan_starts_event_watcher_in_k8s_mode`` — with
   ``COCOA_POD_MODE=true`` the lifespan calls
   :func:`app.core.event_watcher.event_watcher.start` after the system
   startup emit, and :func:`event_watcher.stop` on shutdown.
2. ``test_lifespan_skips_event_watcher_in_local_mode`` — without the
   env var, :func:`start` is NOT called and the singleton's ``_task``
   stays ``None``.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from starlette.testclient import TestClient

# ── helpers ────────────────────────────────────────────────────────────────


class _SpyWatcher:
    """Stand-in for :class:`app.core.event_watcher.EventWatcher`.

    Records calls and assigns a completed future to ``_task`` so
    :func:`start` does not need a real DB round-trip.
    """

    def __init__(self) -> None:
        self._task: asyncio.Future[None] | None = None
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1
        loop = asyncio.get_event_loop()
        self._task = loop.create_future()
        self._task.set_result(None)

    async def stop(self) -> None:
        self.stop_calls += 1
        self._task = None


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW", 100_000,
    )


@asynccontextmanager
async def _swap_db(db_url: str):
    """Re-bind the engine/session factory to the per-test clone before lifespan runs."""
    import app.core.config as cfg
    import app.core.db as db_mod

    previous_url = cfg.settings.DATABASE_URL
    cfg.settings.DATABASE_URL = db_url
    db_mod._engine = None
    db_mod._session_factory = None
    try:
        yield
    finally:
        db_mod._engine = None
        db_mod._session_factory = None
        cfg.settings.DATABASE_URL = previous_url


# ── 1. COCOA_POD_MODE=true → EventWatcher.start ────────────────────────────


@pytest.mark.asyncio
async def test_lifespan_starts_event_watcher_in_k8s_mode(
    monkeypatch: pytest.MonkeyPatch,
    db_url: str,
) -> None:
    """K8s pod mode ⇒ ``event_watcher.start`` fires once and matches stop on exit."""
    monkeypatch.setenv("COCOA_POD_MODE", "true")

    async with _swap_db(db_url):
        spy = _SpyWatcher()
        monkeypatch.setattr("app.core.event_watcher.event_watcher", spy)

        # Importing app lazily so the lifespan reads our env + monkey-patched watcher.
        from app.main import app

        with TestClient(app) as _client:
            # Inside the lifespan yield: spy.start has run, _task assigned.
            assert spy.start_calls == 1
            assert spy._task is not None, (
                "EventWatcher._task must be set while lifespan is up"
            )

        # After the with block the shutdown phase has executed.
        assert spy.stop_calls == 1
        assert spy._task is None


# ── 2. Local mode → EventWatcher.start NOT called ──────────────────────────


@pytest.mark.asyncio
async def test_lifespan_skips_event_watcher_in_local_mode(
    monkeypatch: pytest.MonkeyPatch,
    db_url: str,
) -> None:
    """``COCOA_POD_MODE`` unset ⇒ watcher.start is NOT called."""
    monkeypatch.delenv("COCOA_POD_MODE", raising=False)
    monkeypatch.setenv("COCOA_API_TOKEN", "preexisting-test-token")

    async with _swap_db(db_url):
        spy = _SpyWatcher()
        monkeypatch.setattr("app.core.event_watcher.event_watcher", spy)

        from app.main import app

        with TestClient(app) as _client:
            assert spy.start_calls == 0, (
                "start() must not be called when COCOA_POD_MODE is unset"
            )
            assert spy._task is None
            assert spy.stop_calls == 0

        assert spy.stop_calls == 0
