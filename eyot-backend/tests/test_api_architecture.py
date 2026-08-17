"""Integration tests for the P3 API architecture layer.

Covers the middleware pipeline (RequestID -> CORS -> Auth -> RateLimit),
the standard error envelope, pagination schema serialization, and OpenAPI
metadata. All HTTP tests go through the ``client`` fixture so each test runs
against its own cloned database.
"""

import uuid

import pytest_asyncio
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient

from app.core.errors import NotFoundError, error_response
from app.core.middleware.rate_limit import RateLimitMiddleware
from app.core.pagination import CursorPage, OffsetPage
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def _clear_rate_limits(client: TestClient):
    """Reset the in-memory rate-limit counters before each test.

    The RateLimitMiddleware instance persists on ``app.middleware_stack``
    across tests within a session; without a reset, counting tests would
    leak window state into each other.
    """
    client.get("/health")  # force Starlette to build app.middleware_stack
    mw = app.middleware_stack
    while mw is not None:
        if isinstance(mw, RateLimitMiddleware):
            mw._counters.clear()
            break
        mw = getattr(mw, "app", None)
    yield


async def test_health_endpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}


async def test_no_versioned_health(client: TestClient):
    assert client.get("/api/v1/health").status_code == 404
    # P4 mounted auth/base_classes/entities/workspaces routers.
    # Auth-gated endpoints return 401 (not 404) when no token is provided.
    assert client.get("/api/v1/entities").status_code == 401
    assert client.get("/api/v1/workspaces").status_code == 401


async def test_request_id_header(client: TestClient):
    response = client.get("/health")
    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    # UUID4 shape: 36 chars with dashes in canonical positions.
    assert len(request_id) == 36
    assert uuid.UUID(request_id).version == 4


async def test_cors_headers(client: TestClient):
    response = client.options(
        "/api/v1/error-test",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin in ("*", "http://localhost:5173")
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "GET" in allow_methods


async def test_rate_limit(client: TestClient, monkeypatch):
    # Product default is 600 req/min (SPA polling); pin to 100 to exercise
    # the 429 path deterministically without 600 HTTP round-trips.
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW", 100
    )
    for _ in range(100):
        response = client.get("/api/v1/error-test")
        assert response.status_code != 429
    response = client.get("/api/v1/error-test")
    assert response.status_code == 429
    assert "retry-after" in response.headers
    assert response.headers.get("x-ratelimit-remaining") == "0"


async def test_health_not_rate_limited(client: TestClient):
    for _ in range(101):
        response = client.get("/health")
        assert response.status_code == 200


async def test_middleware_order_on_429(client: TestClient, monkeypatch):
    headers = {"Origin": "http://localhost:5173"}
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW", 100
    )
    for _ in range(100):
        client.get("/api/v1/error-test", headers=headers)
    response = client.get("/api/v1/error-test", headers=headers)
    assert response.status_code == 429
    # RequestID and CORS are outer to RateLimit, so their headers survive a 429.
    assert response.headers.get("x-request-id") is not None
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin in ("*", "http://localhost:5173")


async def test_not_found_error_format(client: TestClient):
    response = client.get("/nonexistent")
    assert response.status_code == 404
    body = response.json()
    # StarletteHTTPException handler converts to the standard envelope,
    # not the default {"detail": "Not Found"}.
    assert "detail" not in body
    assert body["error_code"] == "http.404"
    assert body["message_key"] == "errors.http.404"
    assert "message" in body
    assert body["details"] is None
    # RequestID middleware runs on all requests, so request_id is a UUID.
    assert uuid.UUID(body["request_id"]).version == 4


async def test_error_response_schema():
    response = error_response(NotFoundError("test.code", "test.key", "msg"))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 404
    import json

    content = json.loads(response.body)
    assert content["error_code"] == "test.code"
    assert content["message_key"] == "test.key"
    assert content["message"] == "msg"


async def test_pagination_schema_serialization():
    cursor_page = CursorPage[int](items=[1, 2, 3], next_cursor="abc", total=100)
    cursor_dump = cursor_page.model_dump()
    assert cursor_dump == {"items": [1, 2, 3], "next_cursor": "abc", "total": 100}

    offset_page = OffsetPage[dict](items=[{"a": 1}], offset=0, limit=50, total=1)
    offset_dump = offset_page.model_dump()
    assert offset_dump == {"items": [{"a": 1}], "offset": 0, "limit": 50, "total": 1}


async def test_openapi_json(client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "Eyot API"
    assert len(spec.get("tags", [])) >= 6
