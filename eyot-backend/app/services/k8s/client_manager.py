"""K8sClientManager: singleton caching ApiClient instances."""

import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

from kubernetes_asyncio import client as k8s_client
from kubernetes_asyncio.config import load_kube_config

logger = logging.getLogger(__name__)


@dataclass(slots=True)  # noqa: MUTABLE_OK — cached health state is intentionally mutable
class ClientEntry:
    """Cached K8s client entry."""

    api_client: k8s_client.ApiClient
    auth_type: str = "unknown"
    server: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_health_check: datetime | None = None
    healthy: bool = True


class K8sClientManager:
    """Manage cached Kubernetes API clients."""

    def __init__(self) -> None:
        self._entries: dict[str, ClientEntry] = {}

    async def get_or_create(
        self,
        cluster_id: str,
        credentials_encrypted: str,
        *,
        check_health: bool = False,
    ) -> k8s_client.ApiClient:
        """Get an existing client or create one from kubeconfig YAML."""
        entry = self._entries.get(cluster_id)
        if entry is not None:
            if check_health:
                is_healthy = await self._health_check(entry)
                if not is_healthy:
                    await self.remove(cluster_id)
                    return await self._create(cluster_id, credentials_encrypted)
            return entry.api_client
        return await self._create(cluster_id, credentials_encrypted)

    async def _create(
        self,
        cluster_id: str,
        kubeconfig_yaml: str,
    ) -> k8s_client.ApiClient:
        """Load an ApiClient from a plain kubeconfig YAML string."""
        cfg = k8s_client.Configuration()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=True) as file:
            file.write(kubeconfig_yaml)
            file.flush()
            await load_kube_config(config_file=file.name, client_configuration=cfg)
        api = k8s_client.ApiClient(configuration=cfg)
        self._entries[cluster_id] = ClientEntry(api_client=api)
        return api

    async def _health_check(self, entry: ClientEntry) -> bool:
        """Check whether a cached client can reach the Kubernetes API."""
        try:
            from kubernetes_asyncio.client import VersionApi

            await VersionApi(entry.api_client).get_code()
        except Exception as error:  # noqa: BLE001, BROAD_EXCEPT_OK — K8s client errors are external
            logger.warning("Health check failed: %s", error)
            entry.healthy = False
            return False
        entry.healthy = True
        entry.last_health_check = datetime.now(timezone.utc)
        return True

    async def remove(self, cluster_id: str) -> None:
        """Close and remove a cached client."""
        entry = self._entries.pop(cluster_id, None)
        if entry is not None:
            await entry.api_client.close()

    async def close_all(self) -> None:
        """Close all cached clients and clear the cache."""
        for entry in self._entries.values():
            await entry.api_client.close()
        self._entries.clear()

    async def get_gateway_client(self) -> k8s_client.ApiClient:
        """Get the gateway client using in-cluster or local kubeconfig auth."""
        entry = self._entries.get("_gateway")
        if entry is not None:
            return entry.api_client

        cfg = k8s_client.Configuration()
        service_account_token = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        if os.path.exists(service_account_token):
            from kubernetes_asyncio.config import load_incluster_config

            load_incluster_config(client_configuration=cfg)
            logger.info("gateway client: in-cluster config")
        else:
            gateway_kubeconfig = os.environ.get("GATEWAY_KUBECONFIG")
            if gateway_kubeconfig and os.path.exists(gateway_kubeconfig):
                await load_kube_config(config_file=gateway_kubeconfig, client_configuration=cfg)
                logger.info("gateway client: GATEWAY_KUBECONFIG=%s", gateway_kubeconfig)
            else:
                await load_kube_config(client_configuration=cfg)
                logger.info("gateway client: default kubeconfig (local dev)")

        api = k8s_client.ApiClient(configuration=cfg)
        self._entries["_gateway"] = ClientEntry(api_client=api)
        return api

    def get_status(self) -> dict[str, dict]:  # noqa: ANN401, DICT_OK — status is JSON-shaped API data
        """Return health and creation metadata for cached clients."""
        return {
            client_id: {
                "healthy": entry.healthy,
                "server": entry.server,
                "created_at": entry.created_at.isoformat(),
            }
            for client_id, entry in self._entries.items()
        }


k8s_manager = K8sClientManager()
