"""v4.9 A2b — runtime expansion of gene manifest inline capabilities.

An Entity's effective capability set is the set-union (deduplicated by
capability ``name``) of its ``entity_capabilities`` junction rows and the
inline ``capabilities`` of every attached gene (explicit ``entity_ai_genes``
plus genes inherited from the preset BaseClass). These tests pin:

- attached / inherited gene inline capabilities appear in entity capabilities
- a capability attached both directly and inline in a gene is injected once
  (junction row wins)
- ``migration_hash`` is bumped when a gene is attached / its manifest changes
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.capabilities import (
    attach_entity_ai_gene,
    attach_entity_capability,
    load_entity_capability_dicts,
    upsert_capability,
)
from app.models.ai_gene import AiGene


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


def _names(caps: list[dict]) -> list[str]:
    return [c.get("name") for c in caps if c.get("name")]


def _make_gene(session: AsyncSession, slug: str, inline: list[dict]) -> AiGene:
    gene = AiGene(
        slug=slug,
        name="A2b Gene",
        manifest={"capabilities": inline},
        scope="org",
    )
    session.add(gene)
    return gene


class TestGeneInlineCapabilityExpansion:
    @pytest.mark.asyncio
    async def test_attached_gene_inline_caps_in_entity_capabilities(
        self, session: AsyncSession, entity_factory
    ) -> None:
        entity = await entity_factory()
        gene = _make_gene(
            session,
            f"a2b-gene-{uuid.uuid4().hex[:8]}",
            [
                {"name": "inline-skill-a", "type": "skill", "description": "Inline A"},
                {"name": "inline-tool-b", "type": "mcp"},
            ],
        )
        session.add(gene)
        await session.flush()
        await attach_entity_ai_gene(
            session, entity_id=entity.id, ai_gene_id=gene.id
        )

        caps = await load_entity_capability_dicts(session, entity.id, entity=entity)
        names = _names(caps)
        assert "inline-skill-a" in names
        assert "inline-tool-b" in names
        inline_a = next(c for c in caps if c["name"] == "inline-skill-a")
        assert inline_a["type"] == "skill"
        assert inline_a.get("description") == "Inline A"
        inline_b = next(c for c in caps if c["name"] == "inline-tool-b")
        assert inline_b["type"] == "mcp"
        assert "config_template" not in inline_b

    @pytest.mark.asyncio
    async def test_gene_without_manifest_capabilities_contributes_nothing(
        self, session: AsyncSession, entity_factory
    ) -> None:
        entity = await entity_factory()
        gene = _make_gene(session, f"a2b-empty-{uuid.uuid4().hex[:8]}", [])
        session.add(gene)
        await session.flush()
        await attach_entity_ai_gene(
            session, entity_id=entity.id, ai_gene_id=gene.id
        )

        caps = await load_entity_capability_dicts(session, entity.id, entity=entity)
        assert caps == []


class TestDedupByName:
    @pytest.mark.asyncio
    async def test_same_capability_from_junction_and_gene_injected_once(
        self, session: AsyncSession, entity_factory
    ) -> None:
        entity = await entity_factory()
        cap = await upsert_capability(
            session,
            name="shared-cap",
            cap_type="skill",
            description="market desc",
        )
        await attach_entity_capability(
            session, entity_id=entity.id, capability_id=cap.id
        )
        gene = _make_gene(
            session,
            f"a2b-dedup-{uuid.uuid4().hex[:8]}",
            [
                {"name": "shared-cap", "type": "skill", "description": "gene desc"},
                {"name": "gene-only-cap", "type": "tool", "description": "Only in gene"},
            ],
        )
        session.add(gene)
        await session.flush()
        await attach_entity_ai_gene(
            session, entity_id=entity.id, ai_gene_id=gene.id
        )

        caps = await load_entity_capability_dicts(session, entity.id, entity=entity)
        names = _names(caps)
        assert names.count("shared-cap") == 1
        assert names.count("gene-only-cap") == 1
        # junction row wins the dedup and carries the market metadata
        shared = next(c for c in caps if c["name"] == "shared-cap")
        assert shared.get("description") == "market desc"

    @pytest.mark.asyncio
    async def test_same_inline_capability_across_two_genes_injected_once(
        self, session: AsyncSession, entity_factory
    ) -> None:
        entity = await entity_factory()
        gene_a = _make_gene(
            session,
            f"a2b-multi-a-{uuid.uuid4().hex[:8]}",
            [{"name": "dup-cap", "type": "skill"}],
        )
        gene_b = _make_gene(
            session,
            f"a2b-multi-b-{uuid.uuid4().hex[:8]}",
            [{"name": "dup-cap", "type": "skill"}, {"name": "uniq-cap", "type": "skill"}],
        )
        session.add_all([gene_a, gene_b])
        await session.flush()
        await attach_entity_ai_gene(
            session, entity_id=entity.id, ai_gene_id=gene_a.id
        )
        await attach_entity_ai_gene(
            session, entity_id=entity.id, ai_gene_id=gene_b.id
        )

        caps = await load_entity_capability_dicts(session, entity.id, entity=entity)
        names = _names(caps)
        assert names.count("dup-cap") == 1
        assert "uniq-cap" in names


class TestBaseClassInheritedGeneInlineCaps:
    @pytest.mark.asyncio
    async def test_inherited_gene_inline_caps_expanded_via_preset_slug(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        admin_token, admin_id = _register(
            client,
            f"a2b-i-{uuid.uuid4().hex[:6]}",
            f"a2b-i-{uuid.uuid4().hex[:6]}@t.co",
        )
        bundle = await create_org_bundle(
            admin_id,
            atoms=(
                "can_manage_organization",
                "can_manage_ai_genes",
                "can_manage_namespace",
            ),
        )
        headers = {**_auth(admin_token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={"slug": f"a2b-bc-{uuid.uuid4().hex[:6]}", "name": "Inherit Carrier"},
        )
        assert bc.status_code == 201, bc.text
        bc_id = bc.json()["id"]
        bc_slug = bc.json()["slug"]

        gene = client.post(
            "/api/v1/ai-genes",
            headers=headers,
            json={
                "slug": f"a2b-inh-{uuid.uuid4().hex[:8]}",
                "name": "Inherit Gene",
                "scope": "org",
                "capabilities": [
                    {"name": "inherited-cap", "type": "skill", "description": "From BC"}
                ],
            },
        )
        assert gene.status_code == 201, gene.text
        gene_id = gene.json()["id"]

        linked = client.post(
            f"/api/v1/ai-genes/{gene_id}/attach-base-class",
            headers=headers,
            json={"base_class_id": bc_id},
        )
        assert linked.status_code == 201, linked.text

        ent = client.post(
            "/api/v1/entities",
            headers=_auth(admin_token),
            json={
                "slug": f"a2b-ent-{uuid.uuid4().hex[:6]}",
                "name": "Inherit Entity",
                "rank": "intern",
                "preset_slug": bc_slug,
            },
        )
        assert ent.status_code == 201, ent.text
        entity_id = ent.json()["id"]

        detail = client.get(
            f"/api/v1/entities/{entity_id}", headers=_auth(admin_token)
        )
        assert detail.status_code == 200, detail.text
        assert "inherited-cap" in _names(detail.json()["capabilities"])


class TestMigrationHashSync:
    @pytest.mark.asyncio
    async def test_attach_gene_bumps_entity_migration_hash(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        admin_token, admin_id = _register(
            client,
            f"a2b-h1-{uuid.uuid4().hex[:6]}",
            f"a2b-h1-{uuid.uuid4().hex[:6]}@t.co",
        )
        bundle = await create_org_bundle(
            admin_id,
            atoms=("can_manage_ai_genes", "can_manage_namespace"),
        )
        headers = {**_auth(admin_token), "X-Organization-Id": bundle.org.id}

        gene = client.post(
            "/api/v1/ai-genes",
            headers=headers,
            json={
                "slug": f"a2b-hash-{uuid.uuid4().hex[:8]}",
                "name": "Hash Gene",
                "scope": "org",
                "capabilities": [{"name": "hash-cap", "type": "skill"}],
            },
        )
        assert gene.status_code == 201, gene.text
        gene_id = gene.json()["id"]

        ent = client.post(
            "/api/v1/entities",
            headers=_auth(admin_token),
            json={
                "slug": f"a2b-hash-ent-{uuid.uuid4().hex[:6]}",
                "name": "Hash Entity",
                "rank": "intern",
            },
        )
        assert ent.status_code == 201, ent.text
        entity_id = ent.json()["id"]
        hash_before = ent.json()["migration_hash"]

        attached = client.post(
            f"/api/v1/entities/{entity_id}/ai-genes",
            headers=_auth(admin_token),
            json={"ai_gene_id": gene_id},
        )
        assert attached.status_code == 201, attached.text

        detail = client.get(
            f"/api/v1/entities/{entity_id}", headers=_auth(admin_token)
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["migration_hash"] != hash_before
        assert "hash-cap" in _names(detail.json()["capabilities"])

    @pytest.mark.asyncio
    async def test_update_gene_manifest_bumps_referencing_entities(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        admin_token, admin_id = _register(
            client,
            f"a2b-h2-{uuid.uuid4().hex[:6]}",
            f"a2b-h2-{uuid.uuid4().hex[:6]}@t.co",
        )
        bundle = await create_org_bundle(
            admin_id,
            atoms=("can_manage_ai_genes", "can_manage_namespace"),
        )
        headers = {**_auth(admin_token), "X-Organization-Id": bundle.org.id}

        gene = client.post(
            "/api/v1/ai-genes",
            headers=headers,
            json={
                "slug": f"a2b-upd-{uuid.uuid4().hex[:8]}",
                "name": "Upd Gene",
                "scope": "org",
                "capabilities": [{"name": "cap-a", "type": "skill"}],
            },
        )
        assert gene.status_code == 201, gene.text
        gene_id = gene.json()["id"]

        ent = client.post(
            "/api/v1/entities",
            headers=_auth(admin_token),
            json={
                "slug": f"a2b-upd-ent-{uuid.uuid4().hex[:6]}",
                "name": "Upd Entity",
                "rank": "intern",
            },
        )
        assert ent.status_code == 201, ent.text
        entity_id = ent.json()["id"]

        attached = client.post(
            f"/api/v1/entities/{entity_id}/ai-genes",
            headers=_auth(admin_token),
            json={"ai_gene_id": gene_id},
        )
        assert attached.status_code == 201, attached.text
        detail = client.get(
            f"/api/v1/entities/{entity_id}", headers=_auth(admin_token)
        )
        hash_before = detail.json()["migration_hash"]
        assert "cap-a" in _names(detail.json()["capabilities"])

        patched = client.patch(
            f"/api/v1/ai-genes/{gene_id}",
            headers=headers,
            json={
                "capabilities": [
                    {"name": "cap-b", "type": "skill", "description": "Replaced"}
                ]
            },
        )
        assert patched.status_code == 200, patched.text

        detail = client.get(
            f"/api/v1/entities/{entity_id}", headers=_auth(admin_token)
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["migration_hash"] != hash_before
        names = _names(detail.json()["capabilities"])
        assert "cap-b" in names
        assert "cap-a" not in names

    @pytest.mark.asyncio
    async def test_non_capability_gene_update_does_not_bump(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        admin_token, admin_id = _register(
            client,
            f"a2b-h3-{uuid.uuid4().hex[:6]}",
            f"a2b-h3-{uuid.uuid4().hex[:6]}@t.co",
        )
        bundle = await create_org_bundle(
            admin_id,
            atoms=("can_manage_ai_genes", "can_manage_namespace"),
        )
        headers = {**_auth(admin_token), "X-Organization-Id": bundle.org.id}

        gene = client.post(
            "/api/v1/ai-genes",
            headers=headers,
            json={
                "slug": f"a2b-keep-{uuid.uuid4().hex[:8]}",
                "name": "Keep Gene",
                "scope": "org",
                "capabilities": [{"name": "stable-cap", "type": "skill"}],
            },
        )
        assert gene.status_code == 201, gene.text
        gene_id = gene.json()["id"]

        ent = client.post(
            "/api/v1/entities",
            headers=_auth(admin_token),
            json={
                "slug": f"a2b-keep-ent-{uuid.uuid4().hex[:6]}",
                "name": "Keep Entity",
                "rank": "intern",
            },
        )
        assert ent.status_code == 201, ent.text
        entity_id = ent.json()["id"]

        attached = client.post(
            f"/api/v1/entities/{entity_id}/ai-genes",
            headers=_auth(admin_token),
            json={"ai_gene_id": gene_id},
        )
        assert attached.status_code == 201, attached.text
        detail = client.get(
            f"/api/v1/entities/{entity_id}", headers=_auth(admin_token)
        )
        hash_before = detail.json()["migration_hash"]

        patched = client.patch(
            f"/api/v1/ai-genes/{gene_id}",
            headers=headers,
            json={"name": "Renamed, no capability change"},
        )
        assert patched.status_code == 200, patched.text

        detail = client.get(
            f"/api/v1/entities/{entity_id}", headers=_auth(admin_token)
        )
        assert detail.json()["migration_hash"] == hash_before
