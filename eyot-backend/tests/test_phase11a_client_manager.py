from unittest.mock import AsyncMock, patch

import pytest
from kubernetes_asyncio import client as k8s_client

from app.services.k8s.client_manager import ClientEntry, K8sClientManager


@pytest.mark.asyncio
async def test_get_gateway_client_returns_api_client() -> None:
    manager = K8sClientManager()
    with patch("app.services.k8s.client_manager.load_kube_config", new_callable=AsyncMock):
        first = await manager.get_gateway_client()
        second = await manager.get_gateway_client()

    assert isinstance(first, k8s_client.ApiClient)
    assert second is first
    assert list(manager._entries) == ["_gateway"]
    await manager.close_all()


@pytest.mark.asyncio
async def test_remove_closes_client() -> None:
    manager = K8sClientManager()
    api_client = AsyncMock(spec=k8s_client.ApiClient)
    manager._entries["cluster-1"] = ClientEntry(api_client=api_client)

    await manager.remove("cluster-1")

    assert manager._entries == {}
    api_client.close.assert_awaited_once()
