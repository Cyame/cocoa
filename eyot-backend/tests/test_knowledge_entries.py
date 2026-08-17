"""v4.2 Knowledge System — entries/dimensions CRUD, H2 validation, sentinel, lowercase, isolation.

Pins the normative contract of ``.omo/plans/v4-2-knowledge-system.md`` (and
``.omo/evidence/audit-product-design.md`` §2.3b):

API surface
    CRUD ``/api/v1/knowledge`` and ``/api/v1/knowledge-dimensions``.
    CUD requires ``can_manage_knowledge``; GET list requires login + org
    visibility. POST → 201; DELETE = soft-delete → 204. Errors use the
    standard envelope ``{error_code, message_key, message, details}``.

H2 write-time validation (each row below must 422):
    * scope=system      → all ownership ids must be NULL
    * scope=org         → organization_id required; ns/ws id forbidden
    * scope=namespace   → organization_id + namespace_id required; ws id forbidden
    * scope=workspace   → organization_id + namespace_id + workspace_id required

H3 partial unique (COALESCE sentinel)
    Two active rows with the same (scope, ownership, key) collide — 409 via
    the API, IntegrityError at the DB layer. Same key under different
    scopes / ownership is fine.

Lowercase key
    Keys are normalized to lowercase on write; case variants of the same key
    cannot inject duplicate rows.

Org isolation + system read-only
    Org A's rows are invisible to Org B (list + single GET). ``scope=system``
    rows are visible to every org but not creatable/editable/deletable by
    tenants.

The v4.2 API routes and ``app.models.knowledge`` do not exist yet — every
test here is RED today (404 on the missing routes / ImportError on the
missing models) and turns green only once the implementation lands. Model
imports are deferred into test bodies so one missing module fails individual
tests instead of killing collection.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.organization import Organization

#: A non-zero UUID used to mark an ownership id as "set" in H2 payloads.
_SET_ID = "00000000-0000-0000-0000-000000000001"


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


async def _org_knowledge_manager(
    client: TestClient,
    session: AsyncSession,
    create_org_bundle,
    *,
    atoms: tuple[str, ...] = ("can_manage_knowledge",),
    organization=None,
):
    """Register a non-super-admin user holding *atoms* on an org.

    The first registered user becomes super-admin, so a decoy is registered
    first to keep the returned user a real tenant. ``create_org_bundle`` is
    a conftest fixture and must be passed in by the caller.
    """
    _register(
        client, f"v42-decoy-{uuid.uuid4().hex[:6]}", f"v42-decoy-{uuid.uuid4().hex[:6]}@t.co"
    )
    token, user_id = _register(
        client, f"v42-mgr-{uuid.uuid4().hex[:6]}", f"v42-mgr-{uuid.uuid4().hex[:6]}@t.co"
    )
    bundle = await create_org_bundle(user_id, atoms=atoms, organization=organization)
    return token, user_id, bundle


def _create_entry(
    client: TestClient,
    token: str,
    org_id: str,
    *,
    key: str,
    scope: str,
    organization_id: str | None = None,
    namespace_id: str | None = None,
    workspace_id: str | None = None,
    entity_id: str | None = None,
    instance_id: str | None = None,
    dimension_id: str | None = None,
    title: str = "Title",
    body: str = "Body",
):
    return client.post(
        "/api/v1/knowledge",
        headers={**_auth(token), "X-Organization-Id": org_id},
        json={
            "key": key,
            "title": title,
            "body": body,
            "scope": scope,
            "organization_id": organization_id,
            "namespace_id": namespace_id,
            "workspace_id": workspace_id,
            "entity_id": entity_id,
            "instance_id": instance_id,
            "dimension_id": dimension_id,
        },
    )


class TestKnowledgeCrudPermission:
    """CUD on /api/v1/knowledge requires can_manage_knowledge."""

    @pytest.mark.asyncio
    async def test_post_without_manage_atom_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(
            client, session, create_org_bundle, atoms=("can_view_workspace",)
        )
        resp = _create_entry(
            client, token, bundle.org.id, key=f"k-{uuid.uuid4().hex[:6]}", scope="org"
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_patch_without_manage_atom_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        # Create the entry as a user WITH can_manage_knowledge so the entry
        # exists, then attempt the PATCH as a viewer-only user.
        mgr_token, _, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        created = _create_entry(
            client, mgr_token, bundle.org.id, key=f"k-{uuid.uuid4().hex[:6]}", scope="org",
            organization_id=bundle.org.id,
        )
        assert created.status_code == 201, created.text
        entry_id = created.json()["id"]
        viewer_token, _, _ = await _org_knowledge_manager(
            client, session, create_org_bundle, atoms=("can_view_workspace",)
        )
        resp = client.patch(
            f"/api/v1/knowledge/{entry_id}",
            headers={**_auth(viewer_token), "X-Organization-Id": bundle.org.id},
            json={"body": "attempted"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_delete_without_manage_atom_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        # Create the entry as a user WITH can_manage_knowledge so the entry
        # exists, then attempt the DELETE as a viewer-only user.
        mgr_token, _, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        created = _create_entry(
            client, mgr_token, bundle.org.id, key=f"k-{uuid.uuid4().hex[:6]}", scope="org",
            organization_id=bundle.org.id,
        )
        assert created.status_code == 201, created.text
        entry_id = created.json()["id"]
        viewer_token, _, _ = await _org_knowledge_manager(
            client, session, create_org_bundle, atoms=("can_view_workspace",)
        )
        resp = client.delete(
            f"/api/v1/knowledge/{entry_id}",
            headers={**_auth(viewer_token), "X-Organization-Id": bundle.org.id},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"


class TestKnowledgeCrud:
    @pytest.mark.asyncio
    async def test_list_requires_login(self, client: TestClient) -> None:
        resp = client.get("/api/v1/knowledge")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_org_scope_returns_201_and_lowercases_key(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        resp = _create_entry(
            client,
            token,
            bundle.org.id,
            key="My_Key",
            title="Style",
            body="Use snake_case",
            scope="org",
            organization_id=bundle.org.id,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "id" in body
        assert body["key"] == "my_key"
        assert body["scope"] == "org"
        assert body["organization_id"] == bundle.org.id
        assert body["title"] == "Style"
        assert body["body"] == "Use snake_case"

    @pytest.mark.asyncio
    async def test_create_workspace_scope_returns_201(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
        namespace_factory,
        workspace_factory,
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        ns = await namespace_factory(slug=f"v42-ns-{uuid.uuid4().hex[:6]}")
        ws = await workspace_factory(namespace_id=ns.id)
        await session.commit()
        resp = _create_entry(
            client,
            token,
            bundle.org.id,
            key=f"ws-{uuid.uuid4().hex[:6]}",
            scope="workspace",
            organization_id=bundle.org.id,
            namespace_id=ns.id,
            workspace_id=ws.id,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["scope"] == "workspace"
        assert resp.json()["workspace_id"] == ws.id

    @pytest.mark.asyncio
    async def test_create_with_entity_binding_returns_201(
        self, client: TestClient, session: AsyncSession, create_org_bundle, entity_factory
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        entity = await entity_factory()
        await session.commit()
        resp = _create_entry(
            client,
            token,
            bundle.org.id,
            key=f"bound-{uuid.uuid4().hex[:6]}",
            scope="org",
            organization_id=bundle.org.id,
            entity_id=entity.id,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["entity_id"] == entity.id

    @pytest.mark.asyncio
    async def test_patch_updates_body(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        created = _create_entry(
            client, token, bundle.org.id, key=f"k-{uuid.uuid4().hex[:6]}", scope="org",
            organization_id=bundle.org.id,
        )
        entry_id = created.json()["id"]
        resp = client.patch(
            f"/api/v1/knowledge/{entry_id}",
            headers={**_auth(token), "X-Organization-Id": bundle.org.id},
            json={"body": "updated body"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["body"] == "updated body"

    @pytest.mark.asyncio
    async def test_delete_soft_deletes_row(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        created = _create_entry(
            client, token, bundle.org.id, key=f"k-{uuid.uuid4().hex[:6]}", scope="org",
            organization_id=bundle.org.id,
        )
        entry_id = created.json()["id"]
        resp = client.delete(
            f"/api/v1/knowledge/{entry_id}",
            headers={**_auth(token), "X-Organization-Id": bundle.org.id},
        )
        assert resp.status_code == 204
        KnowledgeEntry, _ = _import_knowledge_models()
        row = (
            await session.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
        ).scalar_one()
        assert row.deleted_at is not None

    @pytest.mark.asyncio
    async def test_get_single_org_row_visible_to_member(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        created = _create_entry(
            client, token, bundle.org.id, key=f"k-{uuid.uuid4().hex[:6]}", scope="org",
            organization_id=bundle.org.id,
        )
        entry_id = created.json()["id"]
        resp = client.get(
            f"/api/v1/knowledge/{entry_id}",
            headers={**_auth(token), "X-Organization-Id": bundle.org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == entry_id

    @pytest.mark.asyncio
    async def test_get_single_org_row_invisible_cross_org(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        a_token, a_user, a_bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        org_b = Organization(slug=f"v42-org-b-{uuid.uuid4().hex[:6]}", name="Org B")
        session.add(org_b)
        await session.flush()
        b_token, b_user, b_bundle = await _org_knowledge_manager(
            client, session, create_org_bundle, organization=org_b
        )
        created = _create_entry(
            client, a_token, a_bundle.org.id, key=f"k-{uuid.uuid4().hex[:6]}", scope="org",
            organization_id=a_bundle.org.id,
        )
        entry_id = created.json()["id"]
        resp = client.get(
            f"/api/v1/knowledge/{entry_id}",
            headers={**_auth(b_token), "X-Organization-Id": b_bundle.org.id},
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "knowledge.not_found"


class TestKnowledgeListOrgIsolation:
    @pytest.mark.asyncio
    async def test_list_org_isolation(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        a_token, a_user, a_bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        org_b = Organization(slug=f"v42-org-b-{uuid.uuid4().hex[:6]}", name="Org B")
        session.add(org_b)
        await session.flush()
        b_token, b_user, b_bundle = await _org_knowledge_manager(
            client, session, create_org_bundle, organization=org_b
        )
        key_a = f"a-{uuid.uuid4().hex[:6]}"
        key_b = f"b-{uuid.uuid4().hex[:6]}"
        r_a = _create_entry(
            client, a_token, a_bundle.org.id, key=key_a, scope="org",
            organization_id=a_bundle.org.id,
        )
        r_b = _create_entry(
            client, b_token, b_bundle.org.id, key=key_b, scope="org",
            organization_id=b_bundle.org.id,
        )
        assert r_a.status_code == 201 and r_b.status_code == 201

        list_a = client.get(
            "/api/v1/knowledge",
            headers={**_auth(a_token), "X-Organization-Id": a_bundle.org.id},
        )
        list_b = client.get(
            "/api/v1/knowledge",
            headers={**_auth(b_token), "X-Organization-Id": b_bundle.org.id},
        )
        assert list_a.status_code == 200
        assert list_b.status_code == 200
        keys_a = {item["key"] for item in list_a.json()["items"]}
        keys_b = {item["key"] for item in list_b.json()["items"]}
        assert key_a in keys_a
        assert key_b not in keys_a
        assert key_b in keys_b
        assert key_a not in keys_b

    @pytest.mark.asyncio
    async def test_system_rows_visible_in_every_org_list(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        a_token, a_user, a_bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        org_b = Organization(slug=f"v42-org-b-{uuid.uuid4().hex[:6]}", name="Org B")
        session.add(org_b)
        await session.flush()
        b_token, b_user, b_bundle = await _org_knowledge_manager(
            client, session, create_org_bundle, organization=org_b
        )
        KnowledgeEntry, _ = _import_knowledge_models()
        session.add(
            KnowledgeEntry(
                key="eyot.collab.passage", title="Passage", body="Neighbor only",
                scope="system",
            )
        )
        await session.commit()

        keys_a = {
            item["key"]
            for item in client.get(
                "/api/v1/knowledge",
                headers={**_auth(a_token), "X-Organization-Id": a_bundle.org.id},
            ).json()["items"]
        }
        keys_b = {
            item["key"]
            for item in client.get(
                "/api/v1/knowledge",
                headers={**_auth(b_token), "X-Organization-Id": b_bundle.org.id},
            ).json()["items"]
        }
        assert "eyot.collab.passage" in keys_a
        assert "eyot.collab.passage" in keys_b


class TestKnowledgeDimensionsCrud:
    @pytest.mark.asyncio
    async def test_dimension_post_requires_manage_atom(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(
            client, session, create_org_bundle, atoms=("can_view_workspace",)
        )
        resp = client.post(
            "/api/v1/knowledge-dimensions",
            headers={**_auth(token), "X-Organization-Id": bundle.org.id},
            json={"name": f"dim-{uuid.uuid4().hex[:6]}"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_dimension_post_returns_201(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        name = f"dim-{uuid.uuid4().hex[:6]}"
        resp = client.post(
            "/api/v1/knowledge-dimensions",
            headers={**_auth(token), "X-Organization-Id": bundle.org.id},
            json={"name": name},
        )
        assert resp.status_code == 201, resp.text
        assert "id" in resp.json()
        assert resp.json()["name"] == name

    @pytest.mark.asyncio
    async def test_dimension_list_returns_items(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        resp = client.get(
            "/api/v1/knowledge-dimensions",
            headers={**_auth(token), "X-Organization-Id": bundle.org.id},
        )
        assert resp.status_code == 200
        assert "items" in resp.json()

    @pytest.mark.asyncio
    async def test_dimension_delete_soft_returns_204(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        created = client.post(
            "/api/v1/knowledge-dimensions",
            headers={**_auth(token), "X-Organization-Id": bundle.org.id},
            json={"name": f"dim-{uuid.uuid4().hex[:6]}"},
        )
        assert created.status_code == 201
        dim_id = created.json()["id"]
        resp = client.delete(
            f"/api/v1/knowledge-dimensions/{dim_id}",
            headers={**_auth(token), "X-Organization-Id": bundle.org.id},
        )
        assert resp.status_code == 204


#: (id, payload) pairs for the H2 write-time scope/FK validation matrix.
_H2_INVALID: list[tuple[str, dict]] = [
    # scope=system — any ownership id set → 422
    ("system-with-org", {"scope": "system", "organization_id": _SET_ID}),
    ("system-with-ns", {"scope": "system", "namespace_id": _SET_ID}),
    ("system-with-ws", {"scope": "system", "workspace_id": _SET_ID}),
    # scope=org — organization_id missing → 422
    ("org-missing-org", {"scope": "org"}),
    # scope=org — ns/ws set → 422
    ("org-with-ns", {"scope": "org", "organization_id": _SET_ID, "namespace_id": _SET_ID}),
    ("org-with-ws", {"scope": "org", "organization_id": _SET_ID, "workspace_id": _SET_ID}),
    # scope=namespace — organization_id or namespace_id missing → 422
    ("ns-missing-org", {"scope": "namespace"}),
    ("ns-missing-org-explicit", {"scope": "namespace", "namespace_id": _SET_ID}),
    ("ns-missing-ns", {"scope": "namespace", "organization_id": _SET_ID}),
    # scope=namespace — ws set → 422
    (
        "ns-with-ws",
        {
            "scope": "namespace",
            "organization_id": _SET_ID,
            "namespace_id": _SET_ID,
            "workspace_id": _SET_ID,
        },
    ),
    # scope=workspace — any of org/ns/ws missing → 422
    ("ws-missing-org", {"scope": "workspace", "namespace_id": _SET_ID, "workspace_id": _SET_ID}),
    ("ws-missing-ns", {"scope": "workspace", "organization_id": _SET_ID, "workspace_id": _SET_ID}),
    ("ws-missing-ws", {"scope": "workspace", "organization_id": _SET_ID, "namespace_id": _SET_ID}),
]


class TestH2WriteTimeValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        [p for _, p in _H2_INVALID],
        ids=[case_id for case_id, _ in _H2_INVALID],
    )
    async def test_invalid_scope_fk_combination_422(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
        payload: dict,
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        resp = _create_entry(
            client,
            token,
            bundle.org.id,
            key=f"h2-{uuid.uuid4().hex[:6]}",
            scope=payload["scope"],
            organization_id=payload.get("organization_id"),
            namespace_id=payload.get("namespace_id"),
            workspace_id=payload.get("workspace_id"),
        )
        assert resp.status_code == 422, (payload, resp.text)
        body = resp.json()
        assert "error_code" in body
        assert "message_key" in body
        assert "message" in body


class TestSentinelUnique:
    @pytest.mark.asyncio
    async def test_same_key_same_scope_conflict_409(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """H3: two active rows with the same (scope, ownership, key) → 409."""
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        key = f"dup-{uuid.uuid4().hex[:6]}"
        first = _create_entry(
            client, token, bundle.org.id, key=key, scope="org",
            organization_id=bundle.org.id,
        )
        assert first.status_code == 201, first.text
        second = _create_entry(
            client, token, bundle.org.id, key=key, scope="org",
            organization_id=bundle.org.id,
        )
        assert second.status_code == 409
        assert "error_code" in second.json()

    @pytest.mark.asyncio
    async def test_same_key_different_scopes_succeed(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
        namespace_factory,
        workspace_factory,
    ) -> None:
        """H3: the same key is legal under different scopes / ownership."""
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        ns = await namespace_factory(slug=f"v42-ns-{uuid.uuid4().hex[:6]}")
        ws = await workspace_factory(namespace_id=ns.id)
        await session.commit()
        org_r = _create_entry(
            client, token, bundle.org.id, key="shared", scope="org",
            organization_id=bundle.org.id,
        )
        ns_r = _create_entry(
            client, token, bundle.org.id, key="shared", scope="namespace",
            organization_id=bundle.org.id, namespace_id=ns.id,
        )
        ws_r = _create_entry(
            client, token, bundle.org.id, key="shared", scope="workspace",
            organization_id=bundle.org.id, namespace_id=ns.id, workspace_id=ws.id,
        )
        assert org_r.status_code == 201, org_r.text
        assert ns_r.status_code == 201, ns_r.text
        assert ws_r.status_code == 201, ws_r.text

    @pytest.mark.asyncio
    async def test_system_sentinel_duplicate_key_conflict(
        self, session: AsyncSession
    ) -> None:
        """H3 for scope=system (all ownership ids NULL): the DB unique index
        must reject a second active row with the same key."""
        KnowledgeEntry, _ = _import_knowledge_models()
        session.add(KnowledgeEntry(key="sys-only", title="A", body="A", scope="system"))
        await session.flush()
        session.add(KnowledgeEntry(key="sys-only", title="B", body="B", scope="system"))
        with pytest.raises(IntegrityError):
            await session.flush()

    def test_sentinel_constant_value(self) -> None:
        """The COALESCE sentinel UUID is pinned by the plan."""
        from app.models.knowledge import SCOPE_NULL_SENTINEL

        assert SCOPE_NULL_SENTINEL == "00000000-0000-0000-0000-000000000000"


class TestLowercaseKey:
    @pytest.mark.asyncio
    async def test_key_normalized_on_write(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        created = _create_entry(
            client, token, bundle.org.id, key="My_Key", scope="org",
            organization_id=bundle.org.id,
        )
        assert created.status_code == 201, created.text
        assert created.json()["key"] == "my_key"
        KnowledgeEntry, _ = _import_knowledge_models()
        rows = (
            await session.execute(
                select(KnowledgeEntry).where(KnowledgeEntry.deleted_at.is_(None))
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].key == "my_key"

    @pytest.mark.asyncio
    async def test_case_variant_same_scope_conflict_409(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        first = _create_entry(
            client, token, bundle.org.id, key="CODING_STYLE", scope="org",
            organization_id=bundle.org.id,
        )
        assert first.status_code == 201, first.text
        second = _create_entry(
            client, token, bundle.org.id, key="coding_style", scope="org",
            organization_id=bundle.org.id,
        )
        assert second.status_code == 409
        assert second.json()["error_code"] != "http.404"

    @pytest.mark.asyncio
    async def test_case_variants_cannot_inject_duplicates(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        first = _create_entry(
            client, token, bundle.org.id, key="CODING_STYLE", scope="org",
            organization_id=bundle.org.id,
        )
        assert first.status_code == 201, first.text
        second = _create_entry(
            client, token, bundle.org.id, key="coding_style", scope="org",
            organization_id=bundle.org.id,
        )
        assert second.status_code == 409
        KnowledgeEntry, _ = _import_knowledge_models()
        rows = (
            await session.execute(
                select(KnowledgeEntry).where(
                    KnowledgeEntry.deleted_at.is_(None),
                    KnowledgeEntry.key == "coding_style",
                )
            )
        ).scalars().all()
        assert len(rows) == 1


class TestSystemScopeReadonly:
    """scope=system rows are platform presets: visible, not tenant-mutable."""

    @pytest.mark.asyncio
    async def test_tenant_cannot_create_system_entry(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        resp = _create_entry(
            client, token, bundle.org.id, key=f"sys-{uuid.uuid4().hex[:6]}", scope="system"
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "scope.system_create_forbidden"

    @pytest.mark.asyncio
    async def test_tenant_cannot_patch_system_entry(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        KnowledgeEntry, _ = _import_knowledge_models()
        sys_entry = KnowledgeEntry(
            key=f"sys-{uuid.uuid4().hex[:6]}", title="S", body="S", scope="system"
        )
        session.add(sys_entry)
        await session.commit()
        resp = client.patch(
            f"/api/v1/knowledge/{sys_entry.id}",
            headers={**_auth(token), "X-Organization-Id": bundle.org.id},
            json={"body": "attempted edit"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "scope.system_readonly"

    @pytest.mark.asyncio
    async def test_tenant_cannot_delete_system_entry(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        token, user_id, bundle = await _org_knowledge_manager(client, session, create_org_bundle)
        KnowledgeEntry, _ = _import_knowledge_models()
        sys_entry = KnowledgeEntry(
            key=f"sys-{uuid.uuid4().hex[:6]}", title="S", body="S", scope="system"
        )
        session.add(sys_entry)
        await session.commit()
        resp = client.delete(
            f"/api/v1/knowledge/{sys_entry.id}",
            headers={**_auth(token), "X-Organization-Id": bundle.org.id},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "scope.system_readonly"


class TestPatchKeyUniqueness:
    """PATCH key-rename must enforce same-scope key uniqueness independent of
    dimension_id.

    The DB partial unique index ``uq_knowledge_entries_active_key`` includes
    ``coalesce(dimension_id)``, so renaming entry B's key to entry A's key in
    the same scope is NOT rejected by the DB when the two entries carry
    different dimensions. The plan contract is "same key unique per scope"
    (dimension-independent, as POST enforces), so PATCH must pre-check too.
    """

    async def _make_dimension(
        self, client: TestClient, token: str, org_id: str
    ) -> str:
        resp = client.post(
            "/api/v1/knowledge-dimensions",
            headers={**_auth(token), "X-Organization-Id": org_id},
            json={"name": f"dim-{uuid.uuid4().hex[:6]}"},
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_patch_key_to_taken_key_different_dimension_409(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """Renaming B's key to A's key at the same scope must 409 even when
        the two rows carry different dimension_id (DB index would otherwise
        be bypassed)."""
        token, user_id, bundle = await _org_knowledge_manager(
            client, session, create_org_bundle
        )
        org_id = bundle.org.id
        dim_a = await self._make_dimension(client, token, org_id)
        dim_b = await self._make_dimension(client, token, org_id)
        key = f"patch-dup-{uuid.uuid4().hex[:6]}"
        a = _create_entry(
            client, token, org_id, key=key, scope="org",
            organization_id=org_id, dimension_id=dim_a,
        )
        assert a.status_code == 201, a.text
        b = _create_entry(
            client, token, org_id, key=f"{key}-b", scope="org",
            organization_id=org_id, dimension_id=dim_b,
        )
        assert b.status_code == 201, b.text
        resp = client.patch(
            f"/api/v1/knowledge/{b.json()['id']}",
            headers={**_auth(token), "X-Organization-Id": org_id},
            json={"key": key},
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "knowledge.key_conflict"
        assert "message_key" in resp.json()

    @pytest.mark.asyncio
    async def test_patch_key_unchanged_does_not_conflict(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """PATCHing an entry to its own key (no-op) must not self-conflict."""
        token, user_id, bundle = await _org_knowledge_manager(
            client, session, create_org_bundle
        )
        org_id = bundle.org.id
        key = f"patch-self-{uuid.uuid4().hex[:6]}"
        a = _create_entry(
            client, token, org_id, key=key, scope="org", organization_id=org_id,
        )
        assert a.status_code == 201, a.text
        resp = client.patch(
            f"/api/v1/knowledge/{a.json()['id']}",
            headers={**_auth(token), "X-Organization-Id": org_id},
            json={"key": key},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["key"] == key

    @pytest.mark.asyncio
    async def test_patch_key_to_free_key_succeeds(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """Renaming to a key no other active row owns at the same scope 200s."""
        token, user_id, bundle = await _org_knowledge_manager(
            client, session, create_org_bundle
        )
        org_id = bundle.org.id
        a = _create_entry(
            client, token, org_id, key=f"k-{uuid.uuid4().hex[:6]}", scope="org",
            organization_id=org_id,
        )
        assert a.status_code == 201, a.text
        new_key = f"renamed-{uuid.uuid4().hex[:6]}"
        resp = client.patch(
            f"/api/v1/knowledge/{a.json()['id']}",
            headers={**_auth(token), "X-Organization-Id": org_id},
            json={"key": new_key},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["key"] == new_key
