"""v4.9 A2a — AiGene manifest capability multi-select serialization contract.

The ai-genes create/update ``capabilities`` field and the combine endpoint
must serialize the manifest ``capabilities`` array through the SAME
constructor (``build_capabilities_manifest``) so the two paths stay
structurally identical. These tests pin that contract:

- create with ``capabilities`` → ``manifest["capabilities"]`` == combine shape
- update with ``capabilities`` → merged into the stored manifest
- ``AiGeneOut.capabilities`` derives from ``manifest["capabilities"]`` (null
  when absent)
- the shared constructor emits exactly ``{"name", "type", "description"}``
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.capabilities import build_capabilities_manifest
from app.models.ai_gene import AiGene
from app.models.capability_market import CapabilityMarketEntry
from app.schemas.ai_gene import (
    CapabilityInline,
    extract_manifest_capabilities,
)


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


COMBINE_CAPABILITIES = [
    {"name": "alpha-cap", "type": "skill", "description": "Test alpha-cap"},
    {"name": "beta-cap", "type": "skill", "description": "Test beta-cap"},
]


class TestSharedConstructor:
    def test_build_capabilities_manifest_emits_three_field_dicts(self) -> None:
        entries = [
            CapabilityInline(
                name="alpha-cap",
                type="skill",
                description="Test alpha-cap",
            ),
            CapabilityInline(name="beta-cap", type="mcp"),
        ]
        out = build_capabilities_manifest(entries)
        assert out == [
            {
                "name": "alpha-cap",
                "type": "skill",
                "description": "Test alpha-cap",
            },
            {"name": "beta-cap", "type": "mcp", "description": None},
        ]

    def test_build_capabilities_manifest_matches_combine_shape(self) -> None:
        entries = [
            CapabilityMarketEntry(
                name=entry["name"],
                type=entry["type"],
                description=entry["description"],
                created_via="manual",
            )
            for entry in COMBINE_CAPABILITIES
        ]
        out = build_capabilities_manifest(entries)
        assert out == COMBINE_CAPABILITIES
        assert all(sorted(item) == ["description", "name", "type"] for item in out)


class TestExtractManifestCapabilities:
    def test_returns_list_when_present(self) -> None:
        manifest = {"capabilities": [{"name": "x", "type": "skill"}]}
        assert extract_manifest_capabilities(manifest) == [
            {"name": "x", "type": "skill"}
        ]

    def test_returns_none_when_absent_or_not_list(self) -> None:
        assert extract_manifest_capabilities(None) is None
        assert extract_manifest_capabilities({}) is None
        assert extract_manifest_capabilities({"capabilities": "not-a-list"}) is None
        assert extract_manifest_capabilities({"tools": []}) is None


class TestAiGeneCapabilitiesRoundTrip:
    @pytest.mark.asyncio
    async def test_create_with_capabilities_isomorphic_to_combine(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"a2a-a-{uuid.uuid4().hex[:6]}", f"a2a-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"a2a-m-{uuid.uuid4().hex[:6]}", f"a2a-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(member_id, atoms=("can_manage_ai_genes",))
        h = {**_auth(member_token), "X-Organization-Id": bundle.org.id}
        slug = f"a2a-gene-{uuid.uuid4().hex[:8]}"

        created = client.post(
            "/api/v1/ai-genes",
            headers=h,
            json={
                "slug": slug,
                "name": "A2a Gene",
                "scope": "org",
                "capabilities": [
                    {"name": "alpha-cap", "type": "skill", "description": "Test alpha-cap"},
                    {"name": "beta-cap", "type": "skill", "description": "Test beta-cap"},
                ],
            },
        )
        assert created.status_code == 201, created.text
        gene_id = created.json()["id"]

        row = await session.get(AiGene, gene_id)
        assert row is not None
        assert row.manifest is not None
        # The capabilities array is byte-identical to the combine inline array
        # (each item exactly {name, type, description}); the create path does
        # not inject combine's extra envelope keys (tools/scripts/...).
        assert row.manifest["capabilities"] == COMBINE_CAPABILITIES
        # capabilities is a derived array, not a stored column.
        assert "capabilities" not in inspect(AiGene).columns.keys()

    @pytest.mark.asyncio
    async def test_create_capabilities_merge_preserves_manifest_keys(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"a2a-b-{uuid.uuid4().hex[:6]}", f"a2a-b-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"a2a-b-{uuid.uuid4().hex[:6]}", f"a2a-b-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(member_id, atoms=("can_manage_ai_genes",))
        h = {**_auth(member_token), "X-Organization-Id": bundle.org.id}

        created = client.post(
            "/api/v1/ai-genes",
            headers=h,
            json={
                "slug": f"a2a-merge-{uuid.uuid4().hex[:8]}",
                "name": "Merge Gene",
                "scope": "org",
                "manifest": {"runtime_config": {"temperature": 0.2}},
                "capabilities": [{"name": "gamma-cap", "type": "tool"}],
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["manifest"]["runtime_config"] == {"temperature": 0.2}
        assert created.json()["manifest"]["capabilities"] == [
            {"name": "gamma-cap", "type": "tool", "description": None}
        ]

    @pytest.mark.asyncio
    async def test_update_capabilities_replaces_manifest_array(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"a2a-c-{uuid.uuid4().hex[:6]}", f"a2a-c-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"a2a-c-{uuid.uuid4().hex[:6]}", f"a2a-c-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(member_id, atoms=("can_manage_ai_genes",))
        h = {**_auth(member_token), "X-Organization-Id": bundle.org.id}
        slug = f"a2a-upd-{uuid.uuid4().hex[:8]}"

        created = client.post(
            "/api/v1/ai-genes",
            headers=h,
            json={"slug": slug, "name": "Upd Gene", "scope": "org"},
        )
        assert created.status_code == 201, created.text
        gene_id = created.json()["id"]

        patched = client.patch(
            f"/api/v1/ai-genes/{gene_id}",
            headers=h,
            json={
                "capabilities": [
                    {"name": "delta-cap", "type": "skill", "description": "Test delta"}
                ]
            },
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["capabilities"] == [
            {"name": "delta-cap", "type": "skill", "description": "Test delta"}
        ]

        row = await session.get(AiGene, gene_id)
        assert row is not None
        assert row.manifest is not None
        assert row.manifest["capabilities"] == [
            {"name": "delta-cap", "type": "skill", "description": "Test delta"}
        ]

    @pytest.mark.asyncio
    async def test_update_without_capabilities_keeps_manifest(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"a2a-d-{uuid.uuid4().hex[:6]}", f"a2a-d-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"a2a-d-{uuid.uuid4().hex[:6]}", f"a2a-d-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(member_id, atoms=("can_manage_ai_genes",))
        h = {**_auth(member_token), "X-Organization-Id": bundle.org.id}
        slug = f"a2a-keep-{uuid.uuid4().hex[:8]}"

        created = client.post(
            "/api/v1/ai-genes",
            headers=h,
            json={
                "slug": slug,
                "name": "Keep Gene",
                "scope": "org",
                "capabilities": [{"name": "zeta-cap", "type": "skill"}],
            },
        )
        assert created.status_code == 201, created.text
        gene_id = created.json()["id"]

        patched = client.patch(
            f"/api/v1/ai-genes/{gene_id}",
            headers=h,
            json={"name": "Renamed"},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["capabilities"] == [
            {"name": "zeta-cap", "type": "skill", "description": None}
        ]


class TestAiGeneOutCapabilities:
    @pytest.mark.asyncio
    async def test_out_capabilities_derived_from_manifest(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"a2a-e-{uuid.uuid4().hex[:6]}", f"a2a-e-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"a2a-e-{uuid.uuid4().hex[:6]}", f"a2a-e-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(member_id, atoms=("can_manage_ai_genes",))
        h = {**_auth(member_token), "X-Organization-Id": bundle.org.id}
        slug = f"a2a-out-{uuid.uuid4().hex[:8]}"

        created = client.post(
            "/api/v1/ai-genes",
            headers=h,
            json={
                "slug": slug,
                "name": "Out Gene",
                "scope": "org",
                "capabilities": COMBINE_CAPABILITIES,
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["capabilities"] == COMBINE_CAPABILITIES
        assert body["capabilities"] == body["manifest"]["capabilities"]

        listed = client.get("/api/v1/ai-genes", headers=h)
        assert listed.status_code == 200, listed.text
        item = next(i for i in listed.json()["items"] if i["id"] == body["id"])
        assert item["capabilities"] == COMBINE_CAPABILITIES

        fetched = client.get(f"/api/v1/ai-genes/{body['id']}", headers=h)
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["capabilities"] == COMBINE_CAPABILITIES

    @pytest.mark.asyncio
    async def test_out_capabilities_null_without_manifest(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"a2a-f-{uuid.uuid4().hex[:6]}", f"a2a-f-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"a2a-f-{uuid.uuid4().hex[:6]}", f"a2a-f-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(member_id, atoms=("can_manage_ai_genes",))
        h = {**_auth(member_token), "X-Organization-Id": bundle.org.id}

        created = client.post(
            "/api/v1/ai-genes",
            headers=h,
            json={"slug": f"a2a-null-{uuid.uuid4().hex[:8]}", "name": "No Cap Gene", "scope": "org"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["capabilities"] is None

    @pytest.mark.asyncio
    async def test_combine_gene_exposes_capabilities_on_out(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        for entry in COMBINE_CAPABILITIES:
            session.add(
                CapabilityMarketEntry(
                    name=entry["name"],
                    type=entry["type"],
                    description=entry["description"],
                    created_via="manual",
                )
            )
        await session.commit()

        _register(client, f"a2a-g-{uuid.uuid4().hex[:6]}", f"a2a-g-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"a2a-g-{uuid.uuid4().hex[:6]}", f"a2a-g-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(member_id, atoms=("can_manage_ai_genes",))
        h = {**_auth(member_token), "X-Organization-Id": bundle.org.id}

        combined = client.post(
            "/api/v1/learning/capabilities/combine",
            headers=h,
            json={
                "capability_names": ["alpha-cap", "beta-cap"],
                "gene_slug": f"a2a-comb-{uuid.uuid4().hex[:8]}",
                "gene_name": "A2a Combine",
            },
        )
        assert combined.status_code == 201, combined.text
        assert combined.json()["manifest_preview"]["capabilities"] == COMBINE_CAPABILITIES

        gene = (
            await session.execute(
                select(AiGene).where(AiGene.slug == combined.json()["new_gene_slug"])
            )
        ).scalar_one()
        assert gene.manifest is not None
        assert gene.manifest["capabilities"] == COMBINE_CAPABILITIES
