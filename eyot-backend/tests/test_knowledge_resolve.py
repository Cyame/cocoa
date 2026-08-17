"""v4.2 Knowledge System — resolve priority (D16/H1) + scaffold injection (M9).

Pins the resolve contract of ``.omo/plans/v4-2-knowledge-system.md``:

- ``GET /api/v1/instances/{id}/knowledge/resolved`` requires ``can_view_workspace``.
- Override priority for a key present at every scope:
  workspace > namespace > org > system.
- ``scope=system`` rows resolve for every org; org-scoped rows never leak
  across orgs.
- Same-scope tie (H1): most recent ``updated_at`` wins, then ``uuid``
  (deterministic).  The sentinel unique key (H3) does not include
  ``dimension_id``, so a same-scope tie is reachable through two rows that
  share key/scope/ownership but differ in dimension — the unique index must
  permit that (the test forces this decision).
- ``build_prompt_scaffold`` (M9) renders a knowledge section (title + body)
  when knowledge is provided, and stays callable without it (backward compat
  is already pinned by ``tests/test_overlay_entity_caps.py``).

Resolved-endpoint response shape pinned by this file::

    {"items": [{"key", "title", "body", "scope", ...}, ...]}

with at most one item per key — the override winner.

The endpoint and ``app.models.knowledge`` / ``app.core.knowledge`` do not
exist yet — every test here is RED today and turns green only once the v4.2
implementation lands. Knowledge imports are deferred into test bodies so one
missing module fails individual tests instead of killing collection.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.prompt_compose import build_prompt_scaffold
from app.models.entity import Entity
from app.models.instance import Instance
from app.models.organization import Namespace, Organization
from app.models.workspace import Workspace


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, username: str, email: str) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "password123"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["id"]


def _import_knowledge_models():
    """Deferred import — raises ImportError (red) until v4.2 models exist."""
    from app.models.knowledge import KnowledgeDimension, KnowledgeEntry

    return KnowledgeEntry, KnowledgeDimension


def _import_resolver():
    """Deferred import of the plan-named resolver seam."""
    from app.core.knowledge import resolve_knowledge_for_instance

    return resolve_knowledge_for_instance


async def _register_viewer(
    client: TestClient, session: AsyncSession, create_org_bundle, *, organization=None
) -> tuple[str, str, SimpleNamespace]:
    """Register a non-super-admin user holding can_view_workspace on *organization*."""
    _register(
        client, f"v42r-decoy-{uuid.uuid4().hex[:6]}", f"v42r-decoy-{uuid.uuid4().hex[:6]}@t.co"
    )
    token, user_id = _register(
        client, f"v42r-user-{uuid.uuid4().hex[:6]}", f"v42r-user-{uuid.uuid4().hex[:6]}@t.co"
    )
    bundle = await create_org_bundle(
        user_id, atoms=("can_view_workspace",), organization=organization
    )
    return token, user_id, bundle


async def _build_stack(session: AsyncSession, *, org=None, slug_prefix: str = "v42") -> SimpleNamespace:
    """Create Namespace + Workspace + Entity + Instance under *org*.

    When *org* is None the default Organization (slug="default") is used.
    """
    if org is None:
        org = (
            await session.execute(
                select(Organization).where(
                    Organization.slug == "default", Organization.deleted_at.is_(None)
                )
            )
        ).scalar_one()
    ns = Namespace(org_id=org.id, slug=f"{slug_prefix}-ns-{uuid.uuid4().hex[:6]}", name="NS")
    session.add(ns)
    await session.flush()
    ws = Workspace(
        namespace_id=ns.id, name="WS", slug=f"{slug_prefix}-ws-{uuid.uuid4().hex[:8]}"
    )
    session.add(ws)
    await session.flush()
    entity = Entity(
        namespace_id=ns.id, name="Ent", slug=f"{slug_prefix}-e-{uuid.uuid4().hex[:8]}",
    )
    session.add(entity)
    await session.flush()
    inst = Instance(
        entity_id=entity.id, workspace_id=ws.id, status="creating",
        proxy_token=str(uuid.uuid4()),
    )
    session.add(inst)
    await session.flush()
    return SimpleNamespace(org=org, namespace=ns, workspace=ws, entity=entity, instance=inst)


async def _insert_entry(
    session: AsyncSession,
    *,
    scope: str,
    key: str,
    body: str,
    title: str = "Title",
    organization_id: str | None = None,
    namespace_id: str | None = None,
    workspace_id: str | None = None,
    dimension_id: str | None = None,
    updated_at: datetime | None = None,
) -> None:
    KnowledgeEntry, _ = _import_knowledge_models()
    kwargs: dict = {
        "key": key,
        "title": title,
        "body": body,
        "scope": scope,
        "organization_id": organization_id,
        "namespace_id": namespace_id,
        "workspace_id": workspace_id,
        "dimension_id": dimension_id,
    }
    if updated_at is not None:
        kwargs["updated_at"] = updated_at
    session.add(KnowledgeEntry(**kwargs))
    await session.flush()


async def _insert_dimension(session: AsyncSession, *, name: str) -> SimpleNamespace:
    _, KnowledgeDimension = _import_knowledge_models()
    dim = KnowledgeDimension(name=name)
    session.add(dim)
    await session.flush()
    return SimpleNamespace(id=dim.id)


def _resolve(client: TestClient, token: str, instance_id: str, *, org_id: str):
    return client.get(
        f"/api/v1/instances/{instance_id}/knowledge/resolved",
        headers={**_auth(token), "X-Organization-Id": org_id},
    )


def _entries_by_key(payload: dict) -> dict[str, dict]:
    """Normalize the resolved response into {key: {key,title,body,scope}}."""
    items = payload["items"]
    assert isinstance(items, list), payload
    out: dict[str, dict] = {}
    for item in items:
        assert isinstance(item, dict), payload
        assert {"key", "title", "body", "scope"} <= set(item), item
        out[item["key"]] = item
    return out


def _as_dict(item) -> dict:
    if isinstance(item, dict):
        return item
    return {
        "key": getattr(item, "key", None),
        "title": getattr(item, "title", None),
        "body": getattr(item, "body", None),
        "scope": getattr(item, "scope", None),
    }


class TestResolvedEndpointPermission:
    @pytest.mark.asyncio
    async def test_resolved_requires_view_workspace_permission(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        # Member holds can_manage_knowledge but NOT can_view_workspace.
        _register(client, f"v42r-d-{uuid.uuid4().hex[:6]}", f"v42r-d-{uuid.uuid4().hex[:6]}@t.co")
        token, user_id = _register(
            client, f"v42r-m-{uuid.uuid4().hex[:6]}", f"v42r-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(user_id, atoms=("can_manage_knowledge",))
        stack = await _build_stack(session, org=bundle.org)
        await session.commit()

        resp = _resolve(client, token, stack.instance.id, org_id=bundle.org.id)
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"


class TestResolvePriority:
    @pytest.mark.asyncio
    async def test_workspace_over_namespace_over_org_over_system(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        """D16: for a key at all four scopes the winner is workspace > ns > org > system."""
        token, user_id, bundle = await _register_viewer(client, session, create_org_bundle)
        stack = await _build_stack(session, org=bundle.org)
        await _insert_entry(session, scope="system", key="style", body="sys-body")
        await _insert_entry(
            session, scope="org", key="style", body="org-body",
            organization_id=stack.org.id,
        )
        await _insert_entry(
            session, scope="namespace", key="style", body="ns-body",
            organization_id=stack.org.id, namespace_id=stack.namespace.id,
        )
        await _insert_entry(
            session, scope="workspace", key="style", body="ws-body",
            organization_id=stack.org.id, namespace_id=stack.namespace.id,
            workspace_id=stack.workspace.id,
        )
        await session.commit()

        resp = _resolve(client, token, stack.instance.id, org_id=stack.org.id)
        assert resp.status_code == 200, resp.text
        entries = _entries_by_key(resp.json())
        assert len(entries) == 1, resp.json()  # one winner per key
        assert entries["style"]["body"] == "ws-body"
        assert entries["style"]["scope"] == "workspace"

    @pytest.mark.asyncio
    async def test_system_visible_to_every_org(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        """scope=system rows resolve for org A and org B alike."""
        a_token, a_user, a_bundle = await _register_viewer(client, session, create_org_bundle)
        org_b = Organization(slug=f"v42r-org-b-{uuid.uuid4().hex[:6]}", name="Org B")
        session.add(org_b)
        await session.flush()
        b_token, b_user, b_bundle = await _register_viewer(
            client, session, create_org_bundle, organization=org_b
        )
        stack_a = await _build_stack(session, org=a_bundle.org, slug_prefix="v42a")
        stack_b = await _build_stack(session, org=org_b, slug_prefix="v42b")
        await _insert_entry(session, scope="system", key="policy", body="sys-policy")
        await session.commit()

        resp_a = _resolve(client, a_token, stack_a.instance.id, org_id=a_bundle.org.id)
        resp_b = _resolve(client, b_token, stack_b.instance.id, org_id=org_b.id)
        assert resp_a.status_code == 200 and resp_b.status_code == 200
        assert _entries_by_key(resp_a.json())["policy"]["body"] == "sys-policy"
        assert _entries_by_key(resp_b.json())["policy"]["body"] == "sys-policy"

    @pytest.mark.asyncio
    async def test_org_rows_do_not_leak_across_orgs(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        """Org B's instance must not resolve org A's org-scoped knowledge."""
        a_token, a_user, a_bundle = await _register_viewer(client, session, create_org_bundle)
        org_b = Organization(slug=f"v42r-org-b-{uuid.uuid4().hex[:6]}", name="Org B")
        session.add(org_b)
        await session.flush()
        b_token, b_user, b_bundle = await _register_viewer(
            client, session, create_org_bundle, organization=org_b
        )
        stack_a = await _build_stack(session, org=a_bundle.org, slug_prefix="v42a")
        stack_b = await _build_stack(session, org=org_b, slug_prefix="v42b")
        await _insert_entry(
            session, scope="org", key="secret", body="a-secret",
            organization_id=a_bundle.org.id,
        )
        await _insert_entry(session, scope="system", key="common", body="sys-common")
        await session.commit()

        resp_a = _resolve(client, a_token, stack_a.instance.id, org_id=a_bundle.org.id)
        resp_b = _resolve(client, b_token, stack_b.instance.id, org_id=org_b.id)
        entries_a = _entries_by_key(resp_a.json())
        entries_b = _entries_by_key(resp_b.json())
        assert entries_a["secret"]["body"] == "a-secret"
        assert "secret" not in entries_b
        assert entries_b["common"]["body"] == "sys-common"


class TestSameScopeTieBreak:
    """H1: same scope + same key → most recent updated_at wins, then uuid.

    The H3 sentinel unique index pins (scope, ownership, key) but not
    ``dimension_id``; these tests create two org-scope rows with the same key
    but different dimensions. For the setup to be legal, the unique index
    must also key on ``dimension_id`` (the v4.2 implementer owns this
    decision — the tests force it).
    """

    @pytest.mark.asyncio
    async def test_newer_updated_at_wins_same_scope(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        token, user_id, bundle = await _register_viewer(client, session, create_org_bundle)
        stack = await _build_stack(session, org=bundle.org)
        dim_old = await _insert_dimension(session, name="dim-old")
        dim_new = await _insert_dimension(session, name="dim-new")
        now = datetime.now(timezone.utc)
        await _insert_entry(
            session, scope="org", key="style", body="older-body",
            organization_id=stack.org.id, dimension_id=dim_old.id,
            updated_at=now - timedelta(seconds=10),
        )
        await _insert_entry(
            session, scope="org", key="style", body="newer-body",
            organization_id=stack.org.id, dimension_id=dim_new.id,
            updated_at=now,
        )
        await session.commit()

        resp = _resolve(client, token, stack.instance.id, org_id=stack.org.id)
        assert resp.status_code == 200, resp.text
        entries = _entries_by_key(resp.json())
        assert len(entries) == 1, resp.json()  # merged per key
        assert entries["style"]["body"] == "newer-body"

    @pytest.mark.asyncio
    async def test_uuid_tie_break_deterministic(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        """Equal updated_at → the uuid tie-break must be deterministic."""
        token, user_id, bundle = await _register_viewer(client, session, create_org_bundle)
        stack = await _build_stack(session, org=bundle.org)
        dim_a = await _insert_dimension(session, name="dim-a")
        dim_b = await _insert_dimension(session, name="dim-b")
        now = datetime.now(timezone.utc)
        await _insert_entry(
            session, scope="org", key="style", body="body-a",
            organization_id=stack.org.id, dimension_id=dim_a.id, updated_at=now,
        )
        await _insert_entry(
            session, scope="org", key="style", body="body-b",
            organization_id=stack.org.id, dimension_id=dim_b.id, updated_at=now,
        )
        await session.commit()

        first = _resolve(client, token, stack.instance.id, org_id=stack.org.id)
        second = _resolve(client, token, stack.instance.id, org_id=stack.org.id)
        winner_a = _entries_by_key(first.json())["style"]["body"]
        winner_b = _entries_by_key(second.json())["style"]["body"]
        assert winner_a in {"body-a", "body-b"}
        assert winner_a == winner_b


class TestResolverSeam:
    """Direct import seam: ``app.core.knowledge.resolve_knowledge_for_instance``."""

    @pytest.mark.asyncio
    async def test_resolver_returns_priority_winner(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _register_viewer(client, session, create_org_bundle)
        stack = await _build_stack(session, org=bundle.org)
        await _insert_entry(session, scope="system", key="style", body="sys-body")
        await _insert_entry(
            session, scope="org", key="style", body="org-body",
            organization_id=stack.org.id,
        )
        await _insert_entry(
            session, scope="namespace", key="style", body="ns-body",
            organization_id=stack.org.id, namespace_id=stack.namespace.id,
        )
        await _insert_entry(
            session, scope="workspace", key="style", body="ws-body",
            organization_id=stack.org.id, namespace_id=stack.namespace.id,
            workspace_id=stack.workspace.id,
        )
        await session.commit()

        resolver = _import_resolver()
        result = await resolver(session, stack.instance)
        rows = [_as_dict(x) for x in result]
        by_key = {r["key"]: r for r in rows}
        assert by_key["style"]["body"] == "ws-body"


class TestScaffoldInjection:
    """M9: build_prompt_scaffold renders a knowledge section.

    The ``knowledge`` kwarg is subject to the M9 hook signature — the
    implementer aligns this test with the final signature if it differs.
    """

    def test_scaffold_includes_knowledge_title_and_body(self) -> None:
        text = build_prompt_scaffold(
            {
                "baseclass_name": "书记",
                "entity_name": "小艾",
                "entity_role_prompt": "负责会议纪要",
            },
            knowledge=[
                {"key": "style-guide", "title": "Style Guide", "body": "Use snake_case in JSON"},
            ],
        )
        assert "Style Guide" in text
        assert "Use snake_case in JSON" in text

    @pytest.mark.asyncio
    async def test_composed_system_prompt_includes_resolved_knowledge(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        """Integration: resolved endpoint → scaffold → SYSTEM prompt contains body."""
        token, user_id, bundle = await _register_viewer(client, session, create_org_bundle)
        stack = await _build_stack(session, org=bundle.org)
        await _insert_entry(
            session, scope="workspace", key="brand", body="Brand voice is calm",
            organization_id=stack.org.id, namespace_id=stack.namespace.id,
            workspace_id=stack.workspace.id,
        )
        await session.commit()

        resp = _resolve(client, token, stack.instance.id, org_id=stack.org.id)
        assert resp.status_code == 200, resp.text
        resolved = resp.json()["items"]
        text = build_prompt_scaffold(
            {"entity_name": "小艾", "entity_role_prompt": "负责会议纪要"},
            knowledge=resolved,
        )
        assert "Brand voice is calm" in text
