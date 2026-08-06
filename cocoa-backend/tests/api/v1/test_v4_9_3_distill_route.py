"""v4.9.3 distill route semantics — slash command + legacy compat (Worker E).

- (a) the LEARNING-family ``/distill`` slash command routes to the NEW
  semantics: Entity memory → capability_market rows (``created_via=distill``),
  NOT a new BaseClass (v4.9.3 design lock B1/B4).
- (b) legacy distill products (BaseClass manifests embedding
  model/prompt/skills/tools/commands strings from the old distill flow)
  still resolve through the overlay without crashing, and
  ``Entity.preset_slug`` references to them still resolve (B4).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.overlay import resolve_instance_agent_config
from app.models.base_class import BaseClass
from app.models.capability_market import CapabilityMarketEntry


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, username: str) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@t.co",
            "password": "password123",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["id"]


def _setup_workspace(
    client: TestClient, token: str, *, name: str, slug: str
) -> str:
    """Create a workspace; the creator is auto-granted workspace atoms (v4.0)."""
    resp = client.post(
        "/api/v1/workspaces",
        headers=_auth(token),
        json={"name": name, "slug": slug},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_entity(client: TestClient, token: str, slug: str) -> str:
    resp = client.post(
        "/api/v1/entities",
        headers=_auth(token),
        json={"name": f"Entity {slug}", "slug": slug},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_instance(
    client: TestClient, token: str, entity_id: str, workspace_id: str
) -> None:
    resp = client.post(
        "/api/v1/instances",
        headers=_auth(token),
        json={"entity_id": entity_id, "workspace_id": workspace_id},
    )
    assert resp.status_code == 201, resp.text


def _create_memory(
    client: TestClient,
    token: str,
    entity_id: str,
    *,
    kind: str,
    key: str | None = None,
    content: str | None = None,
) -> None:
    body: dict = {"entity_id": entity_id, "kind": kind}
    if key is not None:
        body["key"] = key
    if content is not None:
        body["content"] = content
    resp = client.post("/api/v1/memory/entries", headers=_auth(token), json=body)
    assert resp.status_code == 201, resp.text


class TestDistillSlashCommandNewSemantics:
    """(a) @target /distill → capability_market rows, not a BaseClass."""

    @pytest.mark.asyncio
    async def test_distill_creates_capability_market_entry(
        self,
        client: TestClient,
        session: AsyncSession,
    ) -> None:
        token, user_id = _register(
            client, f"v493-route-{uuid.uuid4().hex[:6]}"
        )
        workspace_id = _setup_workspace(
            client,
            token,
            name="V493 Route Workspace",
            slug=f"v493-route-ws-{uuid.uuid4().hex[:6]}",
        )
        entity_slug = f"v493-route-emp-{uuid.uuid4().hex[:6]}"
        entity_id = _create_entity(client, token, entity_slug)
        _create_instance(client, token, entity_id, workspace_id)
        _create_memory(
            client,
            token,
            entity_id,
            kind="lesson",
            key="debug-memory-leak",
            content="A" * 80 + " memory leaks happen when circular refs persist",
        )
        _create_memory(
            client,
            token,
            entity_id,
            kind="experience",
            key="first-exp",
            content="Worked on a big project.",
        )

        from app.core.directive_router import route_turn
        from app.core.event_types import LEARNING_DISTILLATION_COMPLETED
        from app.models.event import Event

        results = await route_turn(
            session, f"@{entity_slug} /distill my-skill", workspace_id, user_id
        )

        assert len(results) == 1
        result = results[0]
        assert result.cmd == "/distill"
        assert result.target_entity == entity_slug
        assert result.engine_used == "heuristic"
        assert result.created_capabilities, "expected distilled capabilities"
        assert all(c["type"] == "skill" for c in result.created_capabilities)

        cap_q = await session.execute(
            select(CapabilityMarketEntry).where(
                CapabilityMarketEntry.created_via == "distill",
                CapabilityMarketEntry.deleted_at.is_(None),
            )
        )
        market_rows = cap_q.scalars().all()
        assert market_rows, "expected capability_market rows via distill"
        assert all(
            row.source_entity_slug == entity_slug for row in market_rows
        )
        distilled_names = {c["name"] for c in result.created_capabilities}
        assert distilled_names == {row.name for row in market_rows}
        assert "debug-memory-leak" in distilled_names

        legacy_preset = await session.execute(
            select(BaseClass).where(
                BaseClass.slug == "base-skill-my-skill",
                BaseClass.deleted_at.is_(None),
            )
        )
        assert (
            legacy_preset.scalar_one_or_none() is None
        ), "old distill flow must no longer create a BaseClass"

        event_result = await session.execute(
            select(Event).where(
                Event.type == LEARNING_DISTILLATION_COMPLETED,
                Event.resource_id == entity_id,
            )
        )
        event = event_result.scalars().first()
        assert event is not None, "expected LEARNING_DISTILLATION_COMPLETED"
        assert event.payload["entity_id"] == entity_id
        assert event.payload["engine_used"] == "heuristic"
        assert event.payload["capability_count"] == len(market_rows)


class TestLegacyDistillManifestCompat:
    """(b) legacy distill BaseClass manifests still resolve via overlay."""

    @pytest.mark.asyncio
    async def test_legacy_manifest_resolves_without_crash(
        self,
        session: AsyncSession,
        entity_factory,
    ) -> None:
        legacy_manifest = {
            "model": "gpt-4o",
            "prompt": "You are a legacy distilled skill about debugging.",
            "skills": ["debugging-checklist", "memory-leak-hunting"],
            "tools": ["read-memory", "grep-logs"],
            "commands": ["debug-memory-leak"],
        }
        base = BaseClass(
            slug=f"legacy-distilled-{uuid.uuid4().hex[:8]}",
            name="Skill: debugging",
            manifest=legacy_manifest,
            scope="system",
        )
        session.add(base)
        await session.flush()

        entity = await entity_factory(
            slug=f"legacy-entity-{uuid.uuid4().hex[:8]}",
            preset_slug=base.slug,
        )

        resolved = await resolve_instance_agent_config(session, entity)

        assert resolved["baseclass_slug"] == base.slug
        assert resolved["system_prompt"] == legacy_manifest["prompt"]
        assert resolved["default_model"] == "gpt-4o"
        assert resolved["commands"] == legacy_manifest["commands"]
        assert resolved["tools"] == legacy_manifest["tools"]
