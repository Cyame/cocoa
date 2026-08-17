"""v4.9.3 schema foundation — knowledge dual-dimension columns.

Worker A slice: the three nullable JSONB columns
(``capability_market.required_knowledge``, ``base_classes.has_knowledge``,
``entities.has_knowledge``) must persist through their API create paths and
round-trip on read, and ``CapabilityCreatedVia.distill`` must exist. The
distill endpoint business logic is a separate worker slice.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.capabilities import upsert_capability
from app.models.base_class import BaseClass
from app.models.capability_market import (
    CapabilityCreatedVia,
    CapabilityMarketEntry,
)
from app.models.entity import Entity


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, username: str, email: str) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "password123",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["id"]


class TestCapabilityRequiredKnowledge:
    @pytest.mark.asyncio
    async def test_create_round_trips_required_knowledge(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        token, user_id = _register(
            client,
            f"v493-c-{uuid.uuid4().hex[:6]}",
            f"v493-c-{uuid.uuid4().hex[:6]}@t.co",
        )
        bundle = await create_org_bundle(
            user_id, atoms=("can_manage_capabilities",)
        )
        h = {**_auth(token), "X-Organization-Id": bundle.org.id}
        required_knowledge = ["knowledge-slug-alpha", "knowledge-slug-beta"]

        created = client.post(
            "/api/v1/capability-market",
            headers=h,
            json={
                "name": f"v493-cap-{uuid.uuid4().hex[:8]}",
                "type": "skill",
                "scope": "org",
                "required_knowledge": required_knowledge,
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["required_knowledge"] == required_knowledge

        fetched = client.get(
            f"/api/v1/capability-market/{body['id']}", headers=h
        )
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["required_knowledge"] == required_knowledge

        row = await session.get(CapabilityMarketEntry, body["id"])
        assert row is not None
        assert row.required_knowledge == required_knowledge

    @pytest.mark.asyncio
    async def test_created_via_enum_has_distill(self) -> None:
        assert CapabilityCreatedVia.distill.value == "distill"

    @pytest.mark.asyncio
    async def test_upsert_capability_persists_required_knowledge(
        self, session: AsyncSession
    ) -> None:
        cap = await upsert_capability(
            session,
            name=f"v493-upsert-{uuid.uuid4().hex[:8]}",
            created_via=CapabilityCreatedVia.distill.value,
            required_knowledge=["knowledge-slug-gamma"],
        )
        assert cap.created_via == "distill"
        assert cap.required_knowledge == ["knowledge-slug-gamma"]


class TestBaseClassHasKnowledge:
    @pytest.mark.asyncio
    async def test_create_round_trips_has_knowledge(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        token, user_id = _register(
            client,
            f"v493-b-{uuid.uuid4().hex[:6]}",
            f"v493-b-{uuid.uuid4().hex[:6]}@t.co",
        )
        bundle = await create_org_bundle(
            user_id, atoms=("can_manage_organization",)
        )
        h = {**_auth(token), "X-Organization-Id": bundle.org.id}
        slug = f"v493-bc-{uuid.uuid4().hex[:8]}"
        has_knowledge = ["knowledge-docs", "knowledge-runbook"]

        created = client.post(
            "/api/v1/base-classes",
            headers=h,
            json={
                "slug": slug,
                "name": "V493 BaseClass",
                "scope": "org",
                "has_knowledge": has_knowledge,
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["has_knowledge"] == has_knowledge

        fetched = client.get(f"/api/v1/base-classes/{slug}", headers=h)
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["has_knowledge"] == has_knowledge

        row = await session.get(BaseClass, body["id"])
        assert row is not None
        assert row.has_knowledge == has_knowledge


class TestEntityHasKnowledge:
    @pytest.mark.asyncio
    async def test_create_round_trips_has_knowledge(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        token, user_id = _register(
            client,
            f"v493-e-{uuid.uuid4().hex[:6]}",
            f"v493-e-{uuid.uuid4().hex[:6]}@t.co",
        )
        bundle = await create_org_bundle(
            user_id, atoms=("can_manage_namespace",)
        )
        h = {**_auth(token), "X-Organization-Id": bundle.org.id}
        has_knowledge = ["knowledge-docs"]

        created = client.post(
            "/api/v1/entities",
            headers=h,
            json={
                "slug": f"v493-ent-{uuid.uuid4().hex[:8]}",
                "name": "V493 Entity",
                "rank": "intern",
                "has_knowledge": has_knowledge,
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["has_knowledge"] == has_knowledge

        fetched = client.get(f"/api/v1/entities/{body['id']}", headers=h)
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["has_knowledge"] == has_knowledge

        row = await session.get(Entity, body["id"])
        assert row is not None
        assert row.has_knowledge == has_knowledge
