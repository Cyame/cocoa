"""v5.2.1 model-catalog endpoint tests — allowlist enrichment with capability fields."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from app.services.llm.model_catalog import ModelInfo


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
            "username": "v521_model_catalog",
            "email": "v521_model_catalog@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "v521_model_catalog", "password": "password123"},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _catalog_entry() -> object:
    return type(
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


def _gpt4o_info() -> ModelInfo:
    return ModelInfo(
        id="gpt-4o",
        name="GPT-4o",
        provider="openai",
        context_length=128000,
        description="Omnivorous flagship",
        reasoning=False,
        tool_call=True,
        attachment=True,
        modalities={"input": ["text", "image"], "output": ["text"]},
        limit_output=16384,
        cost={"input": 2.5, "output": 10.0},
        pricing={"input": 2.5, "output": 10.0},
    )


def _create_catalog_provider(client: TestClient, token: str) -> str:
    with (
        patch(
            "app.api.v1.organizations.model_catalog.get_provider",
            new=AsyncMock(return_value=_catalog_entry()),
        ),
        patch(
            "app.api.v1.organizations.model_catalog.list_models_for_catalog_provider",
            new=AsyncMock(return_value=([_gpt4o_info()], False)),
        ),
    ):
        resp = client.post(
            "/api/v1/organizations/default/providers",
            headers=_auth(token),
            json={
                "origin": "catalog",
                "catalog_provider_id": "openai",
                "api_key_ref": "OPENAI_API_KEY",
            },
        )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_allowlist_branch_enriches_capability_fields(
    client: TestClient, auth_token: str
) -> None:
    """Given: an allowlisted catalog provider with a snapshot match.
    When: GET /model-catalog (allowlist branch).
    Then: entries carry the full capability surface, not just ids."""
    provider_id = _create_catalog_provider(client, auth_token)

    with patch(
        "app.api.v1.model_catalog.model_catalog.list_models",
        new=AsyncMock(return_value=[_gpt4o_info()]),
    ):
        resp = client.get(
            "/api/v1/model-catalog",
            params={"provider_id": provider_id},
            headers=_auth(auth_token),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["degraded"] is False
    assert body["error"] is None
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["id"] == "gpt-4o"
    assert item["name"] == "GPT-4o"
    assert item["provider"] == "openai"
    assert item["context_length"] == 128000
    assert item["description"] == "Omnivorous flagship"
    assert item["reasoning"] is False
    assert item["tool_call"] is True
    assert item["attachment"] is True
    assert item["modalities"] == {"input": ["text", "image"], "output": ["text"]}
    assert item["limit_output"] == 16384
    assert item["cost"] == {"input": 2.5, "output": 10.0}


def test_allowlist_branch_unknown_model_has_none_capabilities(
    client: TestClient, auth_token: str
) -> None:
    """Given: allowlist contains an id absent from the catalog snapshot.
    When: GET /model-catalog.
    Then: the entry is id-only; capabilities are None (portal manual override)."""
    provider_id = _create_catalog_provider(client, auth_token)

    with (
        patch(
            "app.api.v1.organizations.model_catalog.get_provider",
            new=AsyncMock(return_value=_catalog_entry()),
        ),
        patch(
            "app.api.v1.model_catalog.model_catalog.list_models",
            new=AsyncMock(return_value=[_gpt4o_info()]),
        ),
    ):
        # Re-allowlist with an id the snapshot does not know.
        client.patch(
            f"/api/v1/organizations/default/providers/{provider_id}",
            headers=_auth(auth_token),
            json={"models_allowlist": ["glm-5"]},
        )
        resp = client.get(
            "/api/v1/model-catalog",
            params={"provider_id": provider_id},
            headers=_auth(auth_token),
        )
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["id"] == "glm-5"
    assert item["name"] == "glm-5"
    assert item["provider"] == "openai"
    assert item["context_length"] is None
    assert item["reasoning"] is None
    assert item["modalities"] is None
    assert item["cost"] is None
