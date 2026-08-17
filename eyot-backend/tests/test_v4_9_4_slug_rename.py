"""v4.9.4 C2 + C4 — conditional slug rename on BaseClass/Entity/Organization
PATCH endpoints + uniform kebab-case slug validation.

Covers:
- rename success on all three resources
- 409 on uniqueness conflict (all three)
- BaseClass: system-scope PATCH 403, active Entity ``preset_slug`` reference
  blocks with the mandatory details payload, soft-deleted Entity reference
  blocks (soft-deleted counts — permanent-lock semantics)
- Entity: ``Instance.workspace_path`` LIKE lock, ``ComposerMessage.target_entity``
  lock, soft-deleted downstream rows count, underscore-in-old-slug escape
  correctness (no false negative / no false positive)
- Organization: slug == "default" 403, global uniqueness 409
- kebab validation: 422 on empty/whitespace/Chinese/uppercase/underscore,
  200/201 for valid kebab on create, update, and CloneRequest.slug
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.workspace import generate_workspace_path
from app.models.base_class import BaseClass
from app.models.composer_message import ComposerMessage
from app.models.organization import Organization
from app.schemas.clone import CloneRequest


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    return uuid.uuid4().hex[:6]


@pytest.fixture
def auth_token(client: TestClient) -> str:
    """First registered user of an empty deployment is super-admin (P14b)."""
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": f"v494-{_uid()}",
            "email": f"v494-{_uid()}@t.co",
            "password": "password123",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


class TestBaseClassSlugRename:
    @pytest.mark.asyncio
    async def test_rename_success(
        self, client: TestClient, auth_token: str, session: AsyncSession
    ) -> None:
        bc = BaseClass(slug=f"bc-old-{_uid()}", name="Old BC", scope="org")
        session.add(bc)
        await session.commit()
        new_slug = f"bc-new-{_uid()}"

        resp = client.patch(
            f"/api/v1/base-classes/{bc.id}",
            headers=_auth(auth_token),
            json={"slug": new_slug},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["slug"] == new_slug

    @pytest.mark.asyncio
    async def test_rename_same_slug_noop(
        self, client: TestClient, auth_token: str, session: AsyncSession
    ) -> None:
        bc = BaseClass(slug=f"bc-same-{_uid()}", name="BC", scope="org")
        session.add(bc)
        await session.commit()

        resp = client.patch(
            f"/api/v1/base-classes/{bc.id}",
            headers=_auth(auth_token),
            json={"slug": bc.slug, "name": "Renamed"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["slug"] == bc.slug
        assert resp.json()["name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_rename_conflict_409(
        self, client: TestClient, auth_token: str, session: AsyncSession
    ) -> None:
        bc_a = BaseClass(slug=f"bc-a-{_uid()}", name="A", scope="org")
        bc_b = BaseClass(slug=f"bc-b-{_uid()}", name="B", scope="org")
        session.add_all([bc_a, bc_b])
        await session.commit()

        resp = client.patch(
            f"/api/v1/base-classes/{bc_a.id}",
            headers=_auth(auth_token),
            json={"slug": bc_b.slug},
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error_code"] == "base_class.slug_taken"
        assert body["message_key"] == "errors.base_class.slug_taken"

    @pytest.mark.asyncio
    async def test_system_scope_patch_403(
        self, client: TestClient, auth_token: str, session: AsyncSession
    ) -> None:
        bc = BaseClass(slug=f"bc-sys-{_uid()}", name="Sys", scope="system")
        session.add(bc)
        await session.commit()

        resp = client.patch(
            f"/api/v1/base-classes/{bc.id}",
            headers=_auth(auth_token),
            json={"slug": "new-slug"},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["error_code"] == "scope.system_readonly"

    @pytest.mark.asyncio
    async def test_active_entity_reference_blocks_with_details(
        self,
        client: TestClient,
        auth_token: str,
        session: AsyncSession,
        entity_factory,
    ) -> None:
        old_slug = f"bc-ref-{_uid()}"
        bc = BaseClass(slug=old_slug, name="Ref", scope="org")
        session.add(bc)
        await session.flush()
        entity = await entity_factory(preset_slug=old_slug)
        await session.commit()

        resp = client.patch(
            f"/api/v1/base-classes/{bc.id}",
            headers=_auth(auth_token),
            json={"slug": f"bc-ref-new-{_uid()}"},
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error_code"] == "base_class.slug_in_use"
        assert body["message_key"] == "errors.base_class.slug_in_use"
        assert body["details"]["blocking_entities"] == [
            {"id": entity.id, "slug": entity.slug, "deleted": False}
        ]

    @pytest.mark.asyncio
    async def test_soft_deleted_entity_reference_blocks(
        self,
        client: TestClient,
        auth_token: str,
        session: AsyncSession,
        entity_factory,
    ) -> None:
        old_slug = f"bc-del-{_uid()}"
        bc = BaseClass(slug=old_slug, name="Ref", scope="org")
        session.add(bc)
        await session.flush()
        entity = await entity_factory(preset_slug=old_slug)
        entity.soft_delete()
        await session.commit()

        resp = client.patch(
            f"/api/v1/base-classes/{bc.id}",
            headers=_auth(auth_token),
            json={"slug": f"bc-del-new-{_uid()}"},
        )
        assert resp.status_code == 409, resp.text
        blocking = resp.json()["details"]["blocking_entities"]
        assert len(blocking) == 1
        assert blocking[0]["id"] == entity.id
        assert blocking[0]["deleted"] is True

    @pytest.mark.asyncio
    async def test_builtin_preset_slug_immutable(
        self, client: TestClient, auth_token: str
    ) -> None:
        """Builtin presets are read-only even for a super-admin caller."""
        resp = client.get("/api/v1/base-classes/fox", headers=_auth(auth_token))
        assert resp.status_code == 200, resp.text
        preset_id = resp.json()["id"]

        patch = client.patch(
            f"/api/v1/base-classes/{preset_id}",
            headers=_auth(auth_token),
            json={"slug": "hacked-slug"},
        )
        assert patch.status_code == 403, patch.text
        assert patch.json()["error_code"] == "scope.system_readonly"


class TestEntitySlugRename:
    @pytest.mark.asyncio
    async def test_rename_success(
        self,
        client: TestClient,
        auth_token: str,
        session: AsyncSession,
        entity_factory,
    ) -> None:
        entity = await entity_factory()
        await session.commit()
        new_slug = f"ent-new-{_uid()}"

        resp = client.patch(
            f"/api/v1/entities/{entity.id}",
            headers=_auth(auth_token),
            json={"slug": new_slug},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["slug"] == new_slug

    @pytest.mark.asyncio
    async def test_rename_conflict_409(
        self,
        client: TestClient,
        auth_token: str,
        session: AsyncSession,
        entity_factory,
    ) -> None:
        e1 = await entity_factory()
        e2 = await entity_factory()
        await session.commit()

        resp = client.patch(
            f"/api/v1/entities/{e1.id}",
            headers=_auth(auth_token),
            json={"slug": e2.slug},
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error_code"] == "entity.slug_taken"
        assert body["message_key"] == "errors.entity.slug_taken"

    @pytest.mark.asyncio
    async def test_instance_workspace_path_blocks(
        self,
        client: TestClient,
        auth_token: str,
        session: AsyncSession,
        entity_factory,
        instance_factory,
    ) -> None:
        entity = await entity_factory()
        inst = await instance_factory(
            entity_id=entity.id,
            workspace_path=generate_workspace_path(entity.slug, "12345678"),
        )
        await session.commit()

        resp = client.patch(
            f"/api/v1/entities/{entity.id}",
            headers=_auth(auth_token),
            json={"slug": f"ent-lock-{_uid()}"},
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error_code"] == "entity.slug_in_use"
        assert body["message_key"] == "errors.entity.slug_in_use"
        assert body["details"]["instances"] == [
            {"id": inst.id, "deleted": False}
        ]

    @pytest.mark.asyncio
    async def test_composer_message_target_entity_blocks(
        self,
        client: TestClient,
        auth_token: str,
        session: AsyncSession,
        entity_factory,
        workspace_factory,
    ) -> None:
        entity = await entity_factory()
        workspace = await workspace_factory()
        msg = ComposerMessage(
            namespace_id=workspace.namespace_id,
            workspace_id=workspace.id,
            role="user",
            content="hello",
            target_entity=entity.slug,
        )
        session.add(msg)
        await session.commit()

        resp = client.patch(
            f"/api/v1/entities/{entity.id}",
            headers=_auth(auth_token),
            json={"slug": f"ent-lock-{_uid()}"},
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error_code"] == "entity.slug_in_use"
        assert body["details"]["composer_messages"]["count"] == 1
        assert body["details"]["composer_messages"]["message_ids"] == [msg.id]

    @pytest.mark.asyncio
    async def test_soft_deleted_downstream_rows_count(
        self,
        client: TestClient,
        auth_token: str,
        session: AsyncSession,
        entity_factory,
        instance_factory,
        workspace_factory,
    ) -> None:
        entity = await entity_factory()
        inst = await instance_factory(
            entity_id=entity.id,
            workspace_path=generate_workspace_path(entity.slug, "aaaa0001"),
        )
        inst.soft_delete()
        workspace = await workspace_factory()
        msg = ComposerMessage(
            namespace_id=workspace.namespace_id,
            workspace_id=workspace.id,
            role="user",
            content="hello",
            target_entity=entity.slug,
        )
        msg.soft_delete()
        session.add(msg)
        await session.commit()

        resp = client.patch(
            f"/api/v1/entities/{entity.id}",
            headers=_auth(auth_token),
            json={"slug": f"ent-lock-{_uid()}"},
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error_code"] == "entity.slug_in_use"
        assert body["details"]["instances"] == [
            {"id": inst.id, "deleted": True}
        ]
        assert body["details"]["composer_messages"]["count"] == 1
        assert body["details"]["composer_messages"]["message_ids"] == [msg.id]

    @pytest.mark.asyncio
    async def test_underscore_old_slug_escape_no_false_negative(
        self,
        client: TestClient,
        auth_token: str,
        session: AsyncSession,
        entity_factory,
        instance_factory,
    ) -> None:
        """Historical slug with underscores must still be matched literally."""
        entity = await entity_factory(slug="old_agent_x")
        await instance_factory(
            entity_id=entity.id,
            workspace_path=generate_workspace_path("old_agent_x", "deadbeef"),
        )
        await session.commit()

        resp = client.patch(
            f"/api/v1/entities/{entity.id}",
            headers=_auth(auth_token),
            json={"slug": "new-agent"},
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error_code"] == "entity.slug_in_use"

    @pytest.mark.asyncio
    async def test_underscore_escape_no_false_positive(
        self,
        client: TestClient,
        auth_token: str,
        session: AsyncSession,
        entity_factory,
        instance_factory,
    ) -> None:
        """An instance path with a hyphen where the slug has an underscore must
        NOT block the rename (escaped pattern matches literally)."""
        entity = await entity_factory(slug="my_agent")
        await instance_factory(
            entity_id=entity.id,
            workspace_path=".pi/workspace/my-agent-deadbeef/",
        )
        await session.commit()

        resp = client.patch(
            f"/api/v1/entities/{entity.id}",
            headers=_auth(auth_token),
            json={"slug": "brand-new"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["slug"] == "brand-new"


class TestExplicitNullSlugNoop:
    """PATCH {\"slug\": null} must 200 and leave the column unchanged (M2)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "resource",
        ["base_class", "entity", "organization"],
    )
    async def test_explicit_null_slug_is_noop(
        self,
        resource: str,
        client: TestClient,
        auth_token: str,
        session: AsyncSession,
        entity_factory,
    ) -> None:
        if resource == "base_class":
            row = BaseClass(slug=f"bc-null-{_uid()}", name="BC", scope="org")
            session.add(row)
            await session.commit()
            path = f"/api/v1/base-classes/{row.id}"
            original = row.slug
        elif resource == "entity":
            row = await entity_factory()
            await session.commit()
            path = f"/api/v1/entities/{row.id}"
            original = row.slug
        else:
            row = Organization(slug=f"org-null-{_uid()}", name="Org")
            session.add(row)
            await session.commit()
            path = f"/api/v1/organizations/{row.id}"
            original = row.slug

        resp = client.patch(
            path,
            headers=_auth(auth_token),
            json={"slug": None},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["slug"] == original


class TestOrganizationSlugRename:
    @pytest.mark.asyncio
    async def test_rename_success(
        self, client: TestClient, auth_token: str, session: AsyncSession
    ) -> None:
        org = Organization(slug=f"org-old-{_uid()}", name="Org")
        session.add(org)
        await session.commit()
        new_slug = f"org-new-{_uid()}"

        resp = client.patch(
            f"/api/v1/organizations/{org.id}",
            headers=_auth(auth_token),
            json={"slug": new_slug},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["slug"] == new_slug

    @pytest.mark.asyncio
    async def test_default_slug_forbidden_403(
        self, client: TestClient, auth_token: str, session: AsyncSession
    ) -> None:
        org = Organization(slug=f"org-x-{_uid()}", name="X")
        session.add(org)
        await session.commit()

        resp = client.patch(
            f"/api/v1/organizations/{org.id}",
            headers=_auth(auth_token),
            json={"slug": "default"},
        )
        assert resp.status_code == 403, resp.text
        body = resp.json()
        assert body["error_code"] == "organization.default_slug_readonly"
        assert body["message_key"] == "errors.organization.default_slug_readonly"

    @pytest.mark.asyncio
    async def test_default_org_slug_rename_forbidden_bidirectional(
        self, client: TestClient, auth_token: str, session: AsyncSession
    ) -> None:
        """slug 'default' is locked both TO and FROM (by-id and /default)."""
        from sqlalchemy import select

        default_org = (
            await session.execute(
                select(Organization).where(
                    Organization.slug == "default",
                    Organization.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if default_org is None:
            default_org = Organization(slug="default", name="Default")
            session.add(default_org)
            await session.commit()

        resp_default = client.patch(
            "/api/v1/organizations/default",
            headers=_auth(auth_token),
            json={"slug": "renamed"},
        )
        assert resp_default.status_code == 403, resp_default.text
        assert (
            resp_default.json()["error_code"] == "organization.default_slug_readonly"
        )

        resp_by_id = client.patch(
            f"/api/v1/organizations/{default_org.id}",
            headers=_auth(auth_token),
            json={"slug": "renamed"},
        )
        assert resp_by_id.status_code == 403, resp_by_id.text
        assert resp_by_id.json()["error_code"] == "organization.default_slug_readonly"

    @pytest.mark.asyncio
    async def test_rename_conflict_409(
        self, client: TestClient, auth_token: str, session: AsyncSession
    ) -> None:
        org_a = Organization(slug=f"org-a-{_uid()}", name="A")
        org_b = Organization(slug=f"org-b-{_uid()}", name="B")
        session.add_all([org_a, org_b])
        await session.commit()

        resp = client.patch(
            f"/api/v1/organizations/{org_a.id}",
            headers=_auth(auth_token),
            json={"slug": org_b.slug},
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error_code"] == "organization.slug_taken"
        assert body["message_key"] == "errors.organization.slug_taken"


_BAD_KEBAB_SLUGS = (
    "",
    "my slug",
    "中文",
    "MySlug",
    "my_slug",
    "-abc",
    "abc-",
    "a--b",
)


class TestKebabValidation:
    @pytest.mark.asyncio
    async def test_base_class_create_rejects_bad_slugs(
        self, client: TestClient, auth_token: str
    ) -> None:
        for bad in _BAD_KEBAB_SLUGS:
            resp = client.post(
                "/api/v1/base-classes",
                headers=_auth(auth_token),
                json={"slug": bad, "name": "X"},
            )
            assert resp.status_code == 422, f"slug={bad!r} -> {resp.status_code}"
            assert resp.json()["error_code"] == "validation_error"

    @pytest.mark.asyncio
    async def test_entity_create_rejects_bad_slugs(
        self, client: TestClient, auth_token: str
    ) -> None:
        for bad in _BAD_KEBAB_SLUGS:
            resp = client.post(
                "/api/v1/entities",
                headers=_auth(auth_token),
                json={"slug": bad, "name": "X"},
            )
            assert resp.status_code == 422, f"slug={bad!r} -> {resp.status_code}"
            assert resp.json()["error_code"] == "validation_error"

    @pytest.mark.asyncio
    async def test_organization_create_rejects_bad_slugs(
        self, client: TestClient, auth_token: str
    ) -> None:
        for bad in _BAD_KEBAB_SLUGS:
            resp = client.post(
                "/api/v1/organizations",
                headers=_auth(auth_token),
                json={"slug": bad, "name": "X"},
            )
            assert resp.status_code == 422, f"slug={bad!r} -> {resp.status_code}"
            assert resp.json()["error_code"] == "validation_error"

    @pytest.mark.asyncio
    async def test_workspace_create_rejects_bad_slugs(
        self, client: TestClient, auth_token: str
    ) -> None:
        for bad in _BAD_KEBAB_SLUGS:
            resp = client.post(
                "/api/v1/workspaces",
                headers=_auth(auth_token),
                json={"slug": bad, "name": "X"},
            )
            assert resp.status_code == 422, f"slug={bad!r} -> {resp.status_code}"
            assert resp.json()["error_code"] == "validation_error"

    @pytest.mark.asyncio
    async def test_update_rejects_bad_slugs(
        self,
        client: TestClient,
        auth_token: str,
        session: AsyncSession,
        entity_factory,
        workspace_factory,
    ) -> None:
        bc = BaseClass(slug=f"bc-kebab-{_uid()}", name="BC", scope="org")
        entity = await entity_factory()
        org = Organization(slug=f"org-kebab-{_uid()}", name="Org")
        workspace = await workspace_factory(slug=f"ws-kebab-{_uid()}")
        session.add_all([bc, org])
        await session.commit()

        for bad in _BAD_KEBAB_SLUGS:
            resp = client.patch(
                f"/api/v1/base-classes/{bc.id}",
                headers=_auth(auth_token),
                json={"slug": bad},
            )
            assert resp.status_code == 422, f"bc slug={bad!r} -> {resp.status_code}"
            resp = client.patch(
                f"/api/v1/entities/{entity.id}",
                headers=_auth(auth_token),
                json={"slug": bad},
            )
            assert resp.status_code == 422, f"entity slug={bad!r} -> {resp.status_code}"
            resp = client.patch(
                f"/api/v1/organizations/{org.id}",
                headers=_auth(auth_token),
                json={"slug": bad},
            )
            assert resp.status_code == 422, f"org slug={bad!r} -> {resp.status_code}"
            resp = client.patch(
                f"/api/v1/workspaces/{workspace.id}",
                headers=_auth(auth_token),
                json={"slug": bad},
            )
            assert resp.status_code == 422, f"ws slug={bad!r} -> {resp.status_code}"

    def test_create_accepts_valid_kebab(
        self, client: TestClient, auth_token: str
    ) -> None:
        resp = client.post(
            "/api/v1/organizations",
            headers=_auth(auth_token),
            json={"slug": "valid-kebab-2", "name": "Valid"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["slug"] == "valid-kebab-2"

        resp = client.post(
            "/api/v1/base-classes",
            headers=_auth(auth_token),
            json={"slug": "valid-kebab-2", "name": "Valid BC"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["slug"] == "valid-kebab-2"

    def test_clone_request_slug_kebab(self) -> None:
        CloneRequest(slug="valid-kebab-2")
        CloneRequest(slug="a")
        CloneRequest(slug=None)
        with pytest.raises(PydanticValidationError):
            CloneRequest(slug="")
        with pytest.raises(PydanticValidationError):
            CloneRequest(slug="Bad_Slug")
        with pytest.raises(PydanticValidationError):
            CloneRequest(slug="my slug")
        with pytest.raises(PydanticValidationError):
            CloneRequest(slug="中文")
        with pytest.raises(PydanticValidationError):
            CloneRequest(slug="UPPER")
