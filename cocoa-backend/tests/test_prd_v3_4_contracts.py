"""PRD-v3.4: namespace contracts + introduce-entity + cascade."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "v34contracts",
            "email": "v34contracts@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "v34contracts", "password": "password123"},
    )
    return resp.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _default_ns(client: TestClient, token: str) -> dict:
    return client.get("/api/v1/namespaces", headers=_h(token)).json()["items"][0]


def _create_workspace(client: TestClient, token: str, *, slug: str, name: str) -> dict:
    ns = _default_ns(client, token)
    resp = client.post(
        "/api/v1/workspaces",
        headers=_h(token),
        json={"slug": slug, "name": name, "namespace_id": ns["id"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_entity(client: TestClient, token: str, *, slug: str) -> dict:
    ns = _default_ns(client, token)
    resp = client.post(
        "/api/v1/entities",
        headers=_h(token),
        json={
            "slug": slug,
            "name": f"Entity {slug}",
            "namespace_id": ns["id"],
            "rank": "intern",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestNamespaceContracts:
    def test_create_workspace_ensures_namespace_contract(
        self, client: TestClient, auth_token: str
    ) -> None:
        ns = _default_ns(client, auth_token)
        ws = _create_workspace(
            client, auth_token, slug="ws-contract-v34", name="WS Contract"
        )
        assert ws["id"]

        contracts = client.get(
            f"/api/v1/namespaces/{ns['id']}/contracts",
            headers=_h(auth_token),
        )
        assert contracts.status_code == 200, contracts.text
        assert contracts.json()["total"] >= 1
        me = client.get("/api/v1/auth/me", headers=_h(auth_token)).json()
        user_ids = {c["user_id"] for c in contracts.json()["items"]}
        assert me["id"] in user_ids

    def test_list_namespace_contracts(
        self, client: TestClient, auth_token: str
    ) -> None:
        ns = _default_ns(client, auth_token)
        _create_workspace(client, auth_token, slug="ws-list-v34", name="WS List")
        resp = client.get(
            f"/api/v1/namespaces/{ns['id']}/contracts",
            headers=_h(auth_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] >= 1


class TestIntroduceEntity:
    def test_introduce_entity_creates_instance_once(
        self, client: TestClient, auth_token: str
    ) -> None:
        ws = _create_workspace(
            client, auth_token, slug="ws-intro-v34", name="WS Intro"
        )
        entity = _create_entity(client, auth_token, slug="ent-intro-v34")

        resp = client.post(
            f"/api/v1/workspaces/{ws['id']}/introduce-entity",
            headers=_h(auth_token),
            json={"entity_id": entity["id"]},
        )
        assert resp.status_code == 201, resp.text
        first_id = resp.json()["id"]

        again = client.post(
            f"/api/v1/workspaces/{ws['id']}/introduce-entity",
            headers=_h(auth_token),
            json={"entity_id": entity["id"]},
        )
        assert again.status_code == 409, again.text

        listed = client.get(
            f"/api/v1/instances?workspace_id={ws['id']}&entity_id={entity['id']}",
            headers=_h(auth_token),
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["id"] == first_id

    def test_delete_workspace_cascades_instances(
        self, client: TestClient, auth_token: str
    ) -> None:
        ws = _create_workspace(
            client, auth_token, slug="ws-cascade-v34", name="WS Cascade"
        )
        entity = _create_entity(client, auth_token, slug="ent-cascade-v34")

        intro = client.post(
            f"/api/v1/workspaces/{ws['id']}/introduce-entity",
            headers=_h(auth_token),
            json={"entity_id": entity["id"]},
        )
        assert intro.status_code == 201, intro.text
        instance_id = intro.json()["id"]

        deleted = client.delete(
            f"/api/v1/workspaces/{ws['id']}",
            headers=_h(auth_token),
        )
        assert deleted.status_code == 204, deleted.text

        inst = client.get(
            f"/api/v1/instances/{instance_id}",
            headers=_h(auth_token),
        )
        assert inst.status_code == 404

        mems = client.get(
            f"/api/v1/messaging/memberships?workspace_id={ws['id']}",
            headers=_h(auth_token),
        )
        assert mems.status_code == 200
        assert mems.json()["total"] == 0

        ws_get = client.get(
            f"/api/v1/workspaces/{ws['id']}",
            headers=_h(auth_token),
        )
        assert ws_get.status_code == 404

    def test_memberships_kind_user_filter(
        self, client: TestClient, auth_token: str
    ) -> None:
        ws = _create_workspace(
            client, auth_token, slug="ws-kind-v34", name="WS Kind"
        )
        entity = _create_entity(client, auth_token, slug="ent-kind-v34")
        intro = client.post(
            f"/api/v1/workspaces/{ws['id']}/introduce-entity",
            headers=_h(auth_token),
            json={"entity_id": entity["id"]},
        )
        assert intro.status_code == 201, intro.text

        users = client.get(
            f"/api/v1/messaging/memberships?workspace_id={ws['id']}&kind=user",
            headers=_h(auth_token),
        )
        instances = client.get(
            f"/api/v1/messaging/memberships?workspace_id={ws['id']}&kind=instance",
            headers=_h(auth_token),
        )
        assert users.status_code == 200
        assert instances.status_code == 200
        assert users.json()["total"] >= 1
        assert instances.json()["total"] >= 1
        assert all(item["user_id"] for item in users.json()["items"])
        assert all(item["instance_id"] for item in instances.json()["items"])
