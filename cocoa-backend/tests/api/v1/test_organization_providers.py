"""PRD-v3 organization provider + system hub API tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "prd_v3_org",
            "email": "prd_v3_org@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "prd_v3_org", "password": "password123"},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_list_provider_catalog(client: TestClient, auth_token: str) -> None:
    with patch(
        "app.api.v1.provider_catalog.model_catalog.list_providers",
        new=AsyncMock(
            return_value=(
                [
                    type(
                        "P",
                        (),
                        {
                            "id": "openai",
                            "name": "OpenAI",
                            "api": "https://api.openai.com/v1",
                            "inferred_request_format": "completion",
                            "model_count": 2,
                            "doc": None,
                        },
                    )()
                ],
                False,
            )
        ),
    ):
        resp = client.get("/api/v1/provider-catalog", headers=_auth(auth_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is False
    assert body["items"][0]["id"] == "openai"


def test_create_custom_provider_and_list(client: TestClient, auth_token: str) -> None:
    create = client.post(
        "/api/v1/organizations/default/providers",
        headers=_auth(auth_token),
        json={
            "origin": "custom",
            "name": "Corp Gateway",
            "slug": "corp-gateway",
            "request_format": "completion",
            "base_url": "https://llm.example.com/v1",
            "api_key_ref": "CORP_LLM_KEY",
            "default_model": "gpt-4o-mini",
            "verify_ssl": False,
            "models_endpoint_mode": "inherit",
        },
    )
    assert create.status_code == 201, create.text
    row = create.json()
    assert row["origin"] == "custom"
    assert row["verify_ssl"] is False

    listed = client.get(
        "/api/v1/organizations/default/providers?enabled=true",
        headers=_auth(auth_token),
    )
    assert listed.status_code == 200
    assert any(p["id"] == row["id"] for p in listed.json())


def test_duplicate_catalog_enable_409(client: TestClient, auth_token: str) -> None:
    fake_entry = type(
        "P",
        (),
        {
            "id": "openai",
            "name": "OpenAI",
            "api": "https://api.openai.com/v1",
            "inferred_request_format": "completion",
            "model_count": 1,
            "doc": None,
            "raw": {},
        },
    )()
    with (
        patch(
            "app.api.v1.organizations.model_catalog.get_provider",
            new=AsyncMock(return_value=fake_entry),
        ),
        patch(
            "app.api.v1.organizations.model_catalog.list_models_for_catalog_provider",
            new=AsyncMock(
                return_value=(
                    [type("M", (), {"id": "gpt-4o-mini", "name": "mini"})()],
                    False,
                )
            ),
        ),
    ):
        first = client.post(
            "/api/v1/organizations/default/providers",
            headers=_auth(auth_token),
            json={
                "origin": "catalog",
                "catalog_provider_id": "openai",
                "api_key_ref": "OPENAI_API_KEY",
            },
        )
        assert first.status_code == 201, first.text
        second = client.post(
            "/api/v1/organizations/default/providers",
            headers=_auth(auth_token),
            json={
                "origin": "catalog",
                "catalog_provider_id": "openai",
                "api_key_ref": "OPENAI_API_KEY",
            },
        )
    assert second.status_code == 409


def test_set_system_hub_and_generate_description(
    client: TestClient, auth_token: str
) -> None:
    missing = client.post(
        "/api/v1/system-hub/generate-description",
        headers=_auth(auth_token),
        json={"name": "测试眷属"},
    )
    assert missing.status_code == 422
    assert missing.json()["error_code"] == "system_hub.provider_not_set"

    create = client.post(
        "/api/v1/organizations/default/providers",
        headers=_auth(auth_token),
        json={
            "origin": "custom",
            "name": "Hub LLM",
            "slug": "hub-llm",
            "request_format": "completion",
            "base_url": "https://llm.example.com/v1",
            "api_key_ref": "HUB_KEY",
            "default_model": "gpt-4o-mini",
        },
    )
    assert create.status_code == 201, create.text
    pid = create.json()["id"]

    # Provider set but model still empty → model_not_set (not a blanket error).
    only_provider = client.patch(
        "/api/v1/organizations/default/system-hub",
        headers=_auth(auth_token),
        json={"provider_id": pid},
    )
    assert only_provider.status_code == 200
    assert only_provider.json()["configured"] is False

    no_model = client.post(
        "/api/v1/system-hub/generate-description",
        headers=_auth(auth_token),
        json={"name": "测试眷属"},
    )
    assert no_model.status_code == 422
    assert no_model.json()["error_code"] == "system_hub.model_not_set"

    hub = client.patch(
        "/api/v1/organizations/default/system-hub",
        headers=_auth(auth_token),
        json={"provider_id": pid, "model": "gpt-4o-mini"},
    )
    assert hub.status_code == 200
    assert hub.json()["configured"] is True

    fake_resp = type(
        "R",
        (),
        {"content": "这是一段用于测试的眷属职责描述，覆盖协作边界与交付方式。"},
    )()
    with patch(
        "app.api.v1.system_hub.build_llm_client_from_org_provider",
        return_value=type(
            "C",
            (),
            {"complete": AsyncMock(return_value=fake_resp)},
        )(),
    ):
        gen = client.post(
            "/api/v1/system-hub/generate-description",
            headers=_auth(auth_token),
            json={"name": "密士助手"},
        )
    assert gen.status_code == 200, gen.text
    assert len(gen.json()["description"]) > 10


def test_system_hub_generate_resolves_org_scope(
    client: TestClient, auth_token: str
) -> None:
    """Configure the hub on a non-default org; generate-description must read
    the caller's org context (sole active contract), not the default org."""
    org = client.post(
        "/api/v1/organizations",
        headers=_auth(auth_token),
        json={"slug": "scope-world", "name": "Scope World"},
    )
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]

    create = client.post(
        f"/api/v1/organizations/{org_id}/providers",
        headers=_auth(auth_token),
        json={
            "origin": "custom",
            "name": "Scope Hub",
            "slug": "scope-hub",
            "request_format": "completion",
            "base_url": "https://llm.example.com/v1",
            "api_key_ref": "SCOPE_KEY",
            "default_model": "gpt-4o-mini",
        },
    )
    assert create.status_code == 201, create.text
    pid = create.json()["id"]

    hub = client.patch(
        f"/api/v1/organizations/{org_id}/system-hub",
        headers=_auth(auth_token),
        json={"provider_id": pid, "model": "gpt-4o-mini"},
    )
    assert hub.status_code == 200
    assert hub.json()["configured"] is True

    fake_resp = type(
        "R",
        (),
        {"content": "作用域组织的世界描述，覆盖定位与治理边界。"},
    )()
    with patch(
        "app.api.v1.system_hub.build_llm_client_from_org_provider",
        return_value=type(
            "C",
            (),
            {"complete": AsyncMock(return_value=fake_resp)},
        )(),
    ):
        via_header = client.post(
            "/api/v1/system-hub/generate-description",
            headers={
                **_auth(auth_token),
                "X-Organization-Id": org_id,
            },
            json={"name": "Scope World", "kind": "world"},
        )
        via_contract = client.post(
            "/api/v1/system-hub/generate-description",
            headers=_auth(auth_token),
            json={"name": "Scope World", "kind": "world"},
        )
    assert via_header.status_code == 200, via_header.text
    assert via_contract.status_code == 200, via_contract.text


def test_base_classes_hide_internal_by_default(
    client: TestClient, auth_token: str
) -> None:
    resp = client.get("/api/v1/base-classes", headers=_auth(auth_token))
    assert resp.status_code == 200
    slugs = {item["slug"] for item in resp.json().get("items", [])}
    assert "cerebellum-baseclass" not in slugs

    included = client.get(
        "/api/v1/base-classes?include_internal=true",
        headers=_auth(auth_token),
    )
    assert included.status_code == 200
    included_slugs = {item["slug"] for item in included.json().get("items", [])}
    assert "cerebellum-baseclass" in included_slugs
