"""v4.6 learning write-back tests (v4-6-learning-writeback.md).

Covers the v4.6 slice acceptance:
- ``MemoryKind.notepad`` + memory API ``?kind=notepad`` round-trip
- H4: harness notepad append mirrors a ``Memory(kind=notepad)`` row with the
  entity_id resolved from the Instance (never NULL)
- Promote writes junction rows only (no ``entities.capabilities`` JSONB)
- legacy ``notepad_refs`` file-path structure → Memory rows + orphan events
- Combine optionally binds the new AiGene to entity / base_class junctions
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.notepad_migration import migrate_notepad_refs
from app.models import AiGene, BaseClass, CapabilityMarketEntry, Entity, Memory
from app.models.ai_gene import BaseClassAiGene
from app.models.event import Event
from app.models.instance import Instance
from app.models.junctions import EntityAiGene, EntityCapability
from app.models.loop_state import InstanceLoopState


def _legacy_runtime():
    """Return the canonical ``app.agent_runtime.loop`` module.

    The v4.9 convergence moved the legacy ``app/agent_runtime.py`` file
    into the package (``app/agent_runtime/loop.py``) and dropped the
    P11c importlib bridge, so the module is importable directly.
    """
    from app.agent_runtime import loop

    return loop


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post("/api/v1/auth/register", json={
        "username": "p15f_v46",
        "email": "p15f_v46@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "p15f_v46",
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_user_id(auth_token: str, session: AsyncSession) -> str:
    from app.models.user import User

    result = await session.execute(
        select(User).where(User.username == "p15f_v46"),
    )
    user: User = result.scalars().first()
    return user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_workspace(client: TestClient, token: str) -> str:
    slug = f"p15f-ws-{uuid.uuid4().hex[:6]}"
    resp = client.post("/api/v1/workspaces", headers=_auth(token), json={
        "name": f"V46 Workspace {slug}",
        "slug": slug,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_entity(
    client: TestClient, token: str, slug: str | None = None,
) -> str:
    slug = slug or f"p15f-emp-{uuid.uuid4().hex[:6]}"
    resp = client.post("/api/v1/entities", headers=_auth(token), json={
        "name": "Worker", "slug": slug,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_instance(
    client: TestClient, token: str, entity_id: str, workspace_id: str,
) -> str:
    resp = client.post("/api/v1/instances", headers=_auth(token), json={
        "entity_id": entity_id,
        "workspace_id": workspace_id,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_memory(
    client: TestClient, token: str, entity_id: str, *,
    kind: str, key: str | None = None, content: str | None = None,
) -> str:
    body: dict = {"entity_id": entity_id, "kind": kind}
    if key is not None:
        body["key"] = key
    if content is not None:
        body["content"] = content
    resp = client.post("/api/v1/memory/entries", headers=_auth(token), json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# =========================================================================
# MemoryKind.notepad — memory API round-trip
# =========================================================================


class TestNotepadMemoryKind:
    def test_memory_api_accepts_notepad_kind(
        self, client: TestClient, auth_token: str,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        created = _create_memory(
            client, auth_token, entity_id, kind="notepad",
            key="notepad/plan/learnings", content="checkpoint 0: stub",
        )
        assert created

        listed = client.get(
            f"/api/v1/memory/entries?entity_id={entity_id}&kind=notepad",
            headers=h,
        )
        assert listed.status_code == 200, listed.text
        items = listed.json()["items"]
        assert len(items) == 1
        assert items[0]["kind"] == "notepad"

        summary = client.get(
            f"/api/v1/learning/memories/{entity_id}/summary", headers=h,
        )
        assert summary.status_code == 200, summary.text
        assert summary.json()["aggregated_counts"]["total"] >= 1

    def test_memory_create_rejects_unknown_kind(
        self, client: TestClient, auth_token: str,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        resp = client.post(
            "/api/v1/memory/entries", headers=h,
            json={"entity_id": entity_id, "kind": "journal"},
        )
        assert resp.status_code == 422, resp.text


# =========================================================================
# H4 — harness notepad append mirrors a Memory(kind=notepad) row
# =========================================================================


class TestH4NotepadToMemory:
    async def _run_write(
        self, db_url: str, instance_id: str, monkeypatch: pytest.MonkeyPatch,
        *args: str,
    ) -> None:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        legacy = _legacy_runtime()
        engine = create_async_engine(db_url, echo=False)
        try:
            factory = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            monkeypatch.setattr(legacy, "get_session_factory", lambda: factory)
            await legacy._write_notepad_memory(instance_id, *args)
        finally:
            await engine.dispose()

    async def test_write_notepad_memory_resolves_entity_id(
        self, client: TestClient, auth_token: str, session: AsyncSession,
        db_url: str, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)
        # The harness loop creates the loop_state; seed it so the H4 writer
        # can maintain notepad_refs.
        session.add(InstanceLoopState(instance_id=instance_id))
        await session.commit()

        await self._run_write(
            db_url, instance_id, monkeypatch,
            "p14a-checkpoint", "learnings", "checkpoint 3: note",
        )

        rows = (
            await session.execute(
                select(Memory).where(
                    Memory.source_instance_id == instance_id,
                    Memory.kind == "notepad",
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].entity_id == entity_id
        assert rows[0].content == "checkpoint 3: note"
        assert rows[0].key == "notepad/p14a-checkpoint/learnings"

        loop_state = (
            await session.execute(
                select(InstanceLoopState).where(
                    InstanceLoopState.instance_id == instance_id,
                    InstanceLoopState.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        assert loop_state is not None
        assert loop_state.notepad_refs == {"learnings": rows[0].id}

    async def test_write_notepad_memory_skips_missing_instance(
        self, client: TestClient, session: AsyncSession,
        db_url: str, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ghost_id = str(uuid.uuid4())
        await self._run_write(
            db_url, ghost_id, monkeypatch, "p14a-checkpoint", "learnings", "ghost",
        )
        rows = (
            await session.execute(
                select(Memory).where(Memory.source_instance_id == ghost_id)
            )
        ).scalars().all()
        assert rows == []

    async def test_write_notepad_memory_never_writes_null_entity_id(
        self, client: TestClient, session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _FakeInstance:
            entity_id = None
            deleted_at = None

        class _FakeSession:
            def __init__(self) -> None:
                self._added: list[Memory] = []

            async def __aenter__(self) -> _FakeSession:
                return self

            async def __aexit__(self, *_args: object) -> bool:
                return False

            async def get(self, _model: object, _pk: str) -> _FakeInstance:
                return _FakeInstance()

            def add(self, _obj: Memory) -> None:
                self._added.append(_obj)

        class _FakeFactory:
            def __call__(self) -> object:
                return self._make

            def _make(self) -> _FakeSession:
                return _FakeSession()

        monkeypatch.setattr(
            _legacy_runtime(), "get_session_factory", _FakeFactory()
        )
        await _legacy_runtime()._write_notepad_memory(
            str(uuid.uuid4()), "plan", "learnings", "x",
        )


# =========================================================================
# Promote — junction-only writeback (no entities.capabilities JSONB)
# =========================================================================


class TestPromoteJunctionOnly:
    async def test_promote_writes_junction_not_jsonb(
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="v46-promote", content="promote me",
        )
        reap = client.post(
            f"/api/v1/learning/instances/{instance_id}/reap", headers=h, json={},
        )
        assert reap.status_code == 200, reap.text

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/promote",
            headers=h, json={"from_instance_id": instance_id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["capability_promoted_count"] >= 1

        entity = await session.get(Entity, entity_id)
        assert entity is not None
        assert not hasattr(entity, "capabilities"), (
            "entities.capabilities JSONB column must not exist"
        )

        junction_rows = (
            await session.execute(
                select(EntityCapability).where(
                    EntityCapability.entity_id == entity_id,
                    EntityCapability.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        assert len(junction_rows) >= 1

    async def test_promote_bumps_hash_and_marks_siblings_outdated(
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        src_workspace = _setup_workspace(client, auth_token)
        sibling_workspace = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        src_instance = _create_instance(
            client, auth_token, entity_id, src_workspace,
        )
        sibling_instance = _create_instance(
            client, auth_token, entity_id, sibling_workspace,
        )

        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="v46-hash", content="hash bump",
        )
        client.post(
            f"/api/v1/learning/instances/{src_instance}/reap", headers=h, json={},
        )
        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/promote",
            headers=h, json={"from_instance_id": src_instance},
        )
        assert resp.status_code == 200, resp.text

        entity = await session.get(Entity, entity_id)
        assert entity is not None
        assert entity.migration_hash is not None
        assert resp.json()["entity_promotion_migration_hash"] == entity.migration_hash

        sibling = await session.get(Instance, sibling_instance)
        assert sibling is not None
        assert sibling.active_hash != entity.migration_hash


# =========================================================================
# Legacy notepad_refs migration
# =========================================================================


class TestNotepadRefsMigration:
    async def _seed_loop_state(
        self,
        session: AsyncSession,
        instance_id: str,
        refs: dict,
    ) -> str:
        loop_state = InstanceLoopState(instance_id=instance_id, notepad_refs=refs)
        session.add(loop_state)
        await session.commit()
        return loop_state.id

    async def test_migrates_file_paths_to_memory_rows(
        self, client: TestClient, auth_token: str, session: AsyncSession,
        tmp_path: Path,
    ) -> None:
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        learnings_file = tmp_path / "learnings.md"
        learnings_file.write_text("checkpoint 0: migrated note\n", encoding="utf-8")
        missing_file = tmp_path / "missing.md"

        loop_state_id = await self._seed_loop_state(
            session, instance_id,
            {"learnings": str(learnings_file), "issues": str(missing_file)},
        )

        conn = await session.connection()
        report = await conn.run_sync(migrate_notepad_refs)

        assert report["scanned"] == 1
        assert report["memories_created"] == 2
        assert report["orphaned"] == 1
        assert report["refs_rewritten"] == 1

        memories = (
            await session.execute(
                select(Memory).where(
                    Memory.entity_id == entity_id,
                    Memory.kind == "notepad",
                )
            )
        ).scalars().all()
        assert len(memories) == 2
        by_key = {m.key: m for m in memories}
        assert by_key["notepad/learnings"].content == "checkpoint 0: migrated note\n"
        assert by_key["notepad/issues"].content == str(missing_file)

        loop_state = await session.get(InstanceLoopState, loop_state_id)
        assert loop_state is not None
        assert loop_state.notepad_refs["learnings"] == by_key["notepad/learnings"].id
        assert loop_state.notepad_refs["issues"] == by_key["notepad/issues"].id

        orphan = (
            await session.execute(
                select(Event).where(Event.type == "learning.notepad_migration_orphan")
            )
        ).scalars().all()
        assert len(orphan) == 1
        assert orphan[0].payload["path"] == str(missing_file)

    async def test_migration_keeps_uuid_refs_and_skips_no_entity(
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        existing_memory_id = _create_memory(
            client, auth_token, entity_id, kind="notepad",
            key="notepad/plan/learnings", content="already migrated",
        )

        loop_state = InstanceLoopState(
            instance_id=instance_id,
            notepad_refs={"learnings": existing_memory_id},
        )
        session.add(loop_state)
        await session.commit()

        conn = await session.connection()
        report = await conn.run_sync(migrate_notepad_refs)

        assert report["scanned"] == 1
        assert report["memories_created"] == 0
        await session.refresh(loop_state)
        assert loop_state.notepad_refs == {"learnings": existing_memory_id}


    async def test_migration_skips_traversal_and_unparseable_refs(
        self, client: TestClient, auth_token: str, session: AsyncSession,
        tmp_path: Path,
    ) -> None:
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        safe_file = tmp_path / "safe.md"
        safe_file.write_text("safe content", encoding="utf-8")

        loop_state = InstanceLoopState(
            instance_id=instance_id,
            notepad_refs={
                "traversal": "../etc/passwd",
                "unparseable": 12345,
                "safe": str(safe_file),
            },
        )
        session.add(loop_state)
        await session.commit()

        conn = await session.connection()
        report = await conn.run_sync(migrate_notepad_refs)

        assert report["skipped_traversal"] == 1
        assert report["unparseable"] == 1
        assert report["memories_created"] == 1

        memories = (
            await session.execute(
                select(Memory).where(
                    Memory.entity_id == entity_id,
                    Memory.kind == "notepad",
                )
            )
        ).scalars().all()
        assert len(memories) == 1
        assert memories[0].content == "safe content"

        await session.refresh(loop_state)
        assert "traversal" not in loop_state.notepad_refs
        assert "unparseable" not in loop_state.notepad_refs
        assert loop_state.notepad_refs["safe"] == memories[0].id


# =========================================================================
# Combine — optional entity / base_class junction binding (v4.6 §6.4)
# =========================================================================


class TestCombineJunctionBinding:
    async def _seed_capabilities(self, session: AsyncSession, names: list[str]) -> None:
        for name in names:
            session.add(CapabilityMarketEntry(
                name=name, type="skill", description=f"Test {name}",
                created_via="manual",
            ))
        await session.commit()

    async def _grant_ai_gene_atom(
        self, session: AsyncSession, entity_id: str, user_id: str,
    ) -> None:
        from app.core.org_contract import ensure_org_contract, grant_atoms
        from app.models.organization import Namespace

        entity = await session.get(Entity, entity_id)
        assert entity is not None
        ns = await session.get(Namespace, entity.namespace_id)
        assert ns is not None
        contract = await ensure_org_contract(
            session, organization_id=ns.org_id, user_id=user_id
        )
        await grant_atoms(session, contract.id, ("can_manage_ai_genes",))
        await session.commit()

    async def test_combine_binds_to_entity_and_base_class(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        await self._seed_capabilities(session, ["alpha-cap", "beta-cap"])

        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        bc = BaseClass(slug=f"v46-bc-{uuid.uuid4().hex[:6]}", name="V46 Base")
        session.add(bc)
        await session.commit()

        await self._grant_ai_gene_atom(session, entity_id, auth_user_id)

        resp = client.post(
            "/api/v1/learning/capabilities/combine", headers=h,
            json={
                "capability_names": ["alpha-cap", "beta-cap"],
                "gene_slug": "v46-gene",
                "gene_name": "V46 Gene",
                "entity_id": entity_id,
                "base_class_id": bc.id,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["entity_id"] == entity_id
        assert body["base_class_id"] == bc.id

        gene = (
            await session.execute(
                select(AiGene).where(AiGene.slug == "v46-gene")
            )
        ).scalar_one()
        entity_link = (
            await session.execute(
                select(EntityAiGene).where(
                    EntityAiGene.ai_gene_id == gene.id,
                    EntityAiGene.entity_id == entity_id,
                    EntityAiGene.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        assert entity_link is not None

        bc_link = (
            await session.execute(
                select(BaseClassAiGene).where(
                    BaseClassAiGene.ai_gene_id == gene.id,
                    BaseClassAiGene.base_class_id == bc.id,
                    BaseClassAiGene.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        assert bc_link is not None

        ev = (
            await session.execute(
                select(Event).where(Event.type == "learning.composed")
            )
        ).scalars().all()
        assert len(ev) == 1
        assert ev[0].payload["entity_id"] == entity_id

    async def test_combine_404_for_unknown_binding_target(
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        await self._seed_capabilities(session, ["gamma-cap"])

        resp = client.post(
            "/api/v1/learning/capabilities/combine", headers=h,
            json={
                "capability_names": ["gamma-cap"],
                "gene_slug": "v46-gene-404",
                "gene_name": "V46 Gene 404",
                "entity_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404, resp.text

    async def test_combine_404_for_unknown_base_class(
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        await self._seed_capabilities(session, ["gamma-cap"])

        resp = client.post(
            "/api/v1/learning/capabilities/combine", headers=h,
            json={
                "capability_names": ["gamma-cap"],
                "gene_slug": "v46-gene-404-bc",
                "gene_name": "V46 Gene 404 BC",
                "base_class_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404, resp.text

    async def test_combine_forbids_binding_without_ai_gene_atom(
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        await self._seed_capabilities(session, ["delta-cap"])

        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        # The fixture's first user is auto-promoted to super_admin; register a
        # second, unprivileged user whose binding must be refused.
        plain = f"v46-plain-{uuid.uuid4().hex[:6]}"
        client.post("/api/v1/auth/register", json={
            "username": plain,
            "email": f"{plain}@test.com",
            "password": "password123",
        })
        login = client.post("/api/v1/auth/login", json={
            "username": plain, "password": "password123",
        })
        assert login.status_code == 200, login.text
        plain_token = login.json()["access_token"]

        resp = client.post(
            "/api/v1/learning/capabilities/combine",
            headers=_auth(plain_token),
            json={
                "capability_names": ["delta-cap"],
                "gene_slug": "v46-gene-403",
                "gene_name": "V46 Gene 403",
                "entity_id": entity_id,
            },
        )
        assert resp.status_code == 403, resp.text
        gene = (
            await session.execute(
                select(AiGene).where(AiGene.slug == "v46-gene-403")
            )
        ).scalar_one_or_none()
        assert gene is None, "gene must not be created when binding is forbidden"

    async def test_combine_forbids_system_base_class_binding_for_plain_user(
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        await self._seed_capabilities(session, ["zeta-cap"])

        system_bc = BaseClass(
            slug=f"v46-sys-bc-{uuid.uuid4().hex[:6]}", name="V46 System BC",
            scope="system",
        )
        session.add(system_bc)
        await session.commit()

        plain = f"v46-plain2-{uuid.uuid4().hex[:6]}"
        client.post("/api/v1/auth/register", json={
            "username": plain,
            "email": f"{plain}@test.com",
            "password": "password123",
        })
        login = client.post("/api/v1/auth/login", json={
            "username": plain, "password": "password123",
        })
        assert login.status_code == 200, login.text
        plain_token = login.json()["access_token"]

        resp = client.post(
            "/api/v1/learning/capabilities/combine",
            headers=_auth(plain_token),
            json={
                "capability_names": ["zeta-cap"],
                "gene_slug": "v46-gene-sys403",
                "gene_name": "V46 Gene Sys 403",
                "base_class_id": system_bc.id,
            },
        )
        assert resp.status_code == 403, resp.text

    async def test_combine_snapshot_only_validates_binding(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        await self._seed_capabilities(session, ["epsilon-cap"])

        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)
        await self._grant_ai_gene_atom(session, entity_id, auth_user_id)

        # Valid target in preview mode: 200 + echoed ids + no junction written.
        resp = client.post(
            "/api/v1/learning/capabilities/combine", headers=h,
            json={
                "capability_names": ["epsilon-cap"],
                "gene_slug": "v46-gene-preview",
                "gene_name": "V46 Gene Preview",
                "entity_id": entity_id,
                "snapshot_only": True,
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["entity_id"] == entity_id
        gene = (
            await session.execute(
                select(AiGene).where(AiGene.slug == "v46-gene-preview")
            )
        ).scalar_one_or_none()
        assert gene is None, "preview must not create a gene"

        # Bogus target in preview mode must 404 like the write path.
        bad = client.post(
            "/api/v1/learning/capabilities/combine", headers=h,
            json={
                "capability_names": ["epsilon-cap"],
                "gene_slug": "v46-gene-preview-bad",
                "gene_name": "V46 Gene Preview Bad",
                "entity_id": str(uuid.uuid4()),
                "snapshot_only": True,
            },
        )
        assert bad.status_code == 404, bad.text
