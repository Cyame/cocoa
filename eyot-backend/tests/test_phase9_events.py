"""P9 Todo 3: Event query endpoint tests.

Covers the read-only ``GET /api/v1/events`` audit log surface:

1. type_prefix filter (LIKE 'prefix%')
2. All six filters combined (type_prefix + resource_type + resource_id +
   request_id + since + until)
3. Cursor pagination across multiple pages
4. Empty result set when filters match nothing
5. Authentication required (401 without bearer)

Events are inserted directly via the ORM (they are append-only audit
data and do not go through the normal business mutation paths in
these tests). The ``client`` fixture triggers a ``system.startup`` event
on lifespan entry — tests that need a clean baseline account for it.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures local to this module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bump rate limit so test bursts (auth + queries) don't trip 429s."""
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest.fixture
def auth_token(client: TestClient) -> str:
    """Register + login a throwaway user; return the access token."""
    username = f"events_{uuid.uuid4().hex[:8]}"
    client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "password123"},
    )
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    return {"Authorization": f"Bearer {auth_token}"}


async def _seed_event(
    session: AsyncSession,
    *,
    type_: str,
    actor_type: str = "user",
    actor_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    request_id: str | None = None,
    payload: dict | None = None,
) -> str:
    """Insert one Event row directly via the ORM; return its id."""
    from app.models.event import Event

    event = Event(
        type=type_,
        actor_type=actor_type,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        payload=payload if payload is not None else {},
    )
    session.add(event)
    await session.commit()
    return event.id


# ---------------------------------------------------------------------------
# Test 1: type_prefix filter (LIKE 'prefix%')
# ---------------------------------------------------------------------------


async def test_type_prefix_filter_returns_matching_events(
    client: TestClient,
    session: AsyncSession,
    auth_headers: dict,
) -> None:
    """type_prefix='harness.' must return only events whose type starts with it."""
    await _seed_event(session, type_="harness.loop_started", actor_type="system")
    await _seed_event(session, type_="harness.checkpoint", actor_type="system")
    await _seed_event(session, type_="messaging.message_sent", actor_type="user")

    response = client.get(
        "/api/v1/events",
        params={"type_prefix": "harness."},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    types = [item["type"] for item in body["items"]]
    assert "harness.loop_started" in types
    assert "harness.checkpoint" in types
    assert "messaging.message_sent" not in types
    # All returned items must start with the prefix.
    for item in body["items"]:
        assert item["type"].startswith("harness.")


# ---------------------------------------------------------------------------
# Test 2: all six filters combined
# ---------------------------------------------------------------------------


async def test_all_six_filters_combined(
    client: TestClient,
    session: AsyncSession,
    auth_headers: dict,
) -> None:
    """All 6 filters (type_prefix + resource_type + resource_id + request_id
    + since + until) must AND together; non-matching events are excluded."""
    from datetime import datetime, timedelta, timezone

    request_id = f"req-{uuid.uuid4().hex[:8]}"
    target_id = f"inst-{uuid.uuid4().hex[:8]}"
    # ±1h window around now admits events whose created_at defaults to now().
    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(hours=1)).isoformat()
    until_iso = (now + timedelta(hours=1)).isoformat()

    # Match: type_prefix + resource + request_id + time window.
    match_id = await _seed_event(
        session,
        type_="harness.checkpoint",
        actor_type="system",
        resource_type="instance",
        resource_id=target_id,
        request_id=request_id,
    )
    # Same type but wrong resource — must be excluded by resource_id filter.
    await _seed_event(
        session,
        type_="harness.checkpoint",
        resource_type="instance",
        resource_id=f"inst-{uuid.uuid4().hex[:8]}",
    )
    # Same type + resource but wrong request_id — must be excluded.
    await _seed_event(
        session,
        type_="harness.checkpoint",
        resource_type="instance",
        resource_id=target_id,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
    )

    response = client.get(
        "/api/v1/events",
        params={
            "type_prefix": "harness.",
            "resource_type": "instance",
            "resource_id": target_id,
            "request_id": request_id,
            "since": since_iso,
            "until": until_iso,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1, f"Expected exactly 1 match, got {body['items']}"
    item = body["items"][0]
    assert item["id"] == match_id
    assert item["type"] == "harness.checkpoint"
    assert item["resource_type"] == "instance"
    assert item["resource_id"] == target_id
    assert item["request_id"] == request_id
    assert item["actor_type"] == "system"


# ---------------------------------------------------------------------------
# Test 3: cursor pagination
# ---------------------------------------------------------------------------


async def test_cursor_pagination_walks_all_events(
    client: TestClient,
    session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Insert 5 events, walk them with limit=2; every event appears exactly
    once across all pages, and order is newest-first by (created_at, id)."""
    seeded_ids: list[str] = []
    for i in range(5):
        eid = await _seed_event(
            session,
            type_="harness.paginated",
            actor_type="system",
            request_id=f"page-{i}",
        )
        seeded_ids.append(eid)

    walked_ids: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict = {"type_prefix": "harness.paginated", "limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        response = client.get(
            "/api/v1/events",
            params=params,
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        walked_ids.extend(item["id"] for item in body["items"])
        pages += 1
        if body["next_cursor"] is None:
            break
        cursor = body["next_cursor"]
        assert pages < 10, "Pagination did not terminate"

    # All 5 seeded events must have been walked exactly once.
    assert sorted(walked_ids) == sorted(seeded_ids), (
        f"walked {walked_ids} vs seeded {seeded_ids}"
    )
    # Newest-first: created_at must be monotonically non-increasing.
    items_resp = client.get(
        "/api/v1/events",
        params={"type_prefix": "harness.paginated", "limit": 10},
        headers=auth_headers,
    )
    timestamps = [item["created_at"] for item in items_resp.json()["items"]]
    assert timestamps == sorted(timestamps, reverse=True)


# ---------------------------------------------------------------------------
# Test 4: empty result set
# ---------------------------------------------------------------------------


async def test_empty_result_when_no_match(
    client: TestClient,
    session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Filter that matches zero rows must return an empty page + next_cursor=None."""
    await _seed_event(session, type_="messaging.message_sent", actor_type="user")
    await _seed_event(session, type_="harness.checkpoint", actor_type="system")

    response = client.get(
        "/api/v1/events",
        params={"type_prefix": "does.not.exist."},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


# ---------------------------------------------------------------------------
# Test 5: authentication required
# ---------------------------------------------------------------------------


def test_unauthenticated_request_rejected(client: TestClient) -> None:
    """GET /api/v1/events without a bearer token must return 401."""
    response = client.get("/api/v1/events")
    assert response.status_code == 401
    body = response.json()
    assert body["error_code"] in {"auth.unauthorized", "auth.token_missing"}
