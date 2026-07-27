"""P11c Todo 8: Internal endpoint tests.

Covers:

1. ``test_events_emit_writes_db_and_handlers`` — a POST to
   ``/api/v1/internal/events/emit`` with the shared ``COCOA_API_TOKEN``
   returns 201, the event row lands in the database, and a handler
   registered against ``app.core.events`` runs.

2. ``test_invalid_token_returns_401`` — requests without a Bearer
   token, or with a wrong token, are rejected with 401 (and never
   reach the database).

The tests mount :mod:`app.api.v1.internal` on a minimal FastAPI app
(rather than reusing the conftest ``client`` fixture, which is currently
blocked on the P11c Todo 7 agent_runtime split). The per-test database
is the same one the ``session`` fixture provides — they share the
``db_url`` fixture instance within a single test.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

import app.core.db as db_mod
from app.api.deps import get_db
from app.api.v1.internal import router as internal_router
from app.core.db import get_session_factory
from app.core.events import _handlers
from app.models.event import Event

_TEST_TOKEN = "test-cocoa-internal-token"

_AUTH_HEADERS = {"Authorization": f"Bearer {_TEST_TOKEN}"}

_POD_HEARTBEAT = "agent.pod_heartbeat"


@pytest.fixture
def internal_client(db_url: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Minimal TestClient mounting only the internal router.

    Wires :func:`app.api.deps.get_db` to the per-test cloned database
    (same URL the ``session`` fixture uses) and skips the rate-limit
    middleware by mounting on a bare FastAPI app.
    """
    monkeypatch.setattr("app.core.config.settings.DATABASE_URL", db_url)
    db_mod._engine = None
    db_mod._session_factory = None
    factory = get_session_factory()

    async def _override_get_db():  # type: ignore[no-untyped-def]
        async with factory() as s:
            yield s

    app = FastAPI()
    app.include_router(internal_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COCOA_API_TOKEN", _TEST_TOKEN)


@pytest.mark.asyncio
async def test_events_emit_writes_db_and_handlers(
    internal_client: TestClient, session: AsyncSession
) -> None:
    """A POST with the right token persists the event and runs handlers."""
    handler_calls: list[dict] = []

    async def _record(**kwargs: object) -> None:
        handler_calls.append(kwargs)

    _handlers.append((_POD_HEARTBEAT, _record))

    body = {
        "type": _POD_HEARTBEAT,
        "actor_type": "agent_pod",
        "actor_id": "pod-abc",
        "resource_type": "instance",
        "resource_id": "inst-xyz",
        "payload": {"tick": 42, "alive": True},
    }

    try:
        resp = internal_client.post(
            "/api/v1/internal/events/emit",
            json=body,
            headers=_AUTH_HEADERS,
        )
    finally:
        _handlers[:] = [h for h in _handlers if h[1] is not _record]

    assert resp.status_code == 201, resp.text
    event_id = resp.json()["event_id"]
    assert event_id

    assert len(handler_calls) == 1
    assert handler_calls[0]["event_type"] == _POD_HEARTBEAT
    assert handler_calls[0]["payload"] == {"tick": 42, "alive": True}

    result = await session.execute(select(Event).where(Event.id == event_id))
    row = result.scalar_one()
    assert row.type == _POD_HEARTBEAT
    assert row.actor_type == "agent_pod"
    assert row.actor_id == "pod-abc"
    assert row.resource_type == "instance"
    assert row.resource_id == "inst-xyz"
    assert row.payload == {"tick": 42, "alive": True}


@pytest.mark.asyncio
async def test_invalid_token_returns_401(
    internal_client: TestClient, session: AsyncSession
) -> None:
    """Missing header and wrong-token requests both 401 and write nothing."""
    body = {
        "type": _POD_HEARTBEAT,
        "actor_type": "agent_pod",
        "actor_id": "pod-abc",
        "resource_type": "instance",
        "resource_id": "inst-xyz",
        "payload": {"tick": 1},
    }

    resp_missing = internal_client.post(
        "/api/v1/internal/events/emit", json=body
    )
    assert resp_missing.status_code == 401

    resp_wrong = internal_client.post(
        "/api/v1/internal/events/emit",
        json=body,
        headers={"Authorization": "Bearer not-the-real-token"},
    )
    assert resp_wrong.status_code == 401

    result = await session.execute(
        select(Event).where(Event.type == _POD_HEARTBEAT)
    )
    assert result.scalars().all() == []
