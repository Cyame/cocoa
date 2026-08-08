"""Integration tests for the BaseClass market list endpoint (T5 onboarding).

Covers:
- GET /api/v1/base-classes (offset-paginated list of active BaseClass rows)
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models import BaseClass
from app.models.user import User


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post("/api/v1/auth/register", json={
        "username": "p15f_bc",
        "email": "p15f_bc@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "p15f_bc",
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_user_id(auth_token: str, session: AsyncSession) -> str:
    result = await session.execute(
        select(User).where(User.username == "p15f_bc"),
    )
    user: User = result.scalars().first()
    return user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestBaseClassesList:
    """Tests for the GET /base-classes endpoint."""

    def test_list_returns_seeded_builtins(
        self, client: TestClient, auth_token: str,
    ) -> None:
        resp = client.get("/api/v1/base-classes", headers=_auth(auth_token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 5
        slugs = {item["slug"] for item in body["items"]}
        assert "fox" in slugs
        # cerebellum-baseclass is API-hidden by default (PRD-v3)
        assert "cerebellum-baseclass" not in slugs

    async def test_list_returns_active_base_classes(
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        for slug in ["x", "y", "z"]:
            session.add(BaseClass(
                slug=slug, name=f"BaseClass {slug}",
                display_name=f"bc.{slug}",
                description=f"Test {slug}",
                manifest={"default_capabilities": []},
                version="0.1.0",
                tags=["test"],
                scope="system",
            ))
        await session.commit()

        resp = client.get("/api/v1/base-classes", headers=_auth(auth_token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 3
        slugs = {item["slug"] for item in body["items"]}
        assert {"x", "y", "z"}.issubset(slugs)

    async def test_list_orders_by_created_at_descending(
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        """Newest BaseClass first — critical for the onboarding modal's first-page affordance."""
        import asyncio
        for slug in ["first", "second", "third"]:
            session.add(BaseClass(slug=slug, name=f"BC {slug}", scope="system"))
            await session.commit()
            await asyncio.sleep(0.01)  # ensure distinct timestamps

        resp = client.get("/api/v1/base-classes", headers=_auth(auth_token))
        assert resp.status_code == 200, resp.text
        slugs = [item["slug"] for item in resp.json()["items"]]
        # Custom rows must appear before older seeded builtins.
        assert slugs[:3] == ["third", "second", "first"]

    async def test_list_excludes_soft_deleted(
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        alive = BaseClass(slug="alive", name="Alive", scope="system")
        deleted = BaseClass(slug="deleted", name="Deleted", scope="system")
        session.add_all([alive, deleted])
        await session.commit()
        deleted.soft_delete()
        await session.commit()

        resp = client.get("/api/v1/base-classes", headers=_auth(auth_token))
        assert resp.status_code == 200, resp.text
        slugs = {item["slug"] for item in resp.json()["items"]}
        assert "alive" in slugs
        assert "deleted" not in slugs

    async def test_list_paginates(
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        for i in range(5):
            session.add(BaseClass(slug=f"bc-{i}", name=f"BC {i}"))
        await session.commit()

        resp = client.get(
            "/api/v1/base-classes?limit=2&offset=0",
            headers=_auth(auth_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 5
        assert body["limit"] == 2
        assert body["offset"] == 0
        assert len(body["items"]) == 2

        resp2 = client.get(
            "/api/v1/base-classes?limit=2&offset=2",
            headers=_auth(auth_token),
        )
        assert resp2.status_code == 200, resp2.text
        assert len(resp2.json()["items"]) == 2

    def test_list_requires_auth(
        self, client: TestClient,
    ) -> None:
        resp = client.get("/api/v1/base-classes")
        assert resp.status_code == 401, resp.text
