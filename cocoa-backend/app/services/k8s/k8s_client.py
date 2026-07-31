"""K8sClient: single-cluster operation wrapper around kubernetes-asyncio.

Non-watch operations live here. Watch + streaming operations are split
into k8s_client_watch.py and attached via :class:`K8sClientWatchMixin`
to keep this file under the 500 LOC ceiling.
"""

import logging
from datetime import datetime, timezone

from kubernetes_asyncio import client as k8s_client

from app.services.k8s.k8s_client_watch import K8sClientWatchMixin

logger = logging.getLogger(__name__)


class K8sClient(K8sClientWatchMixin):
    """Wraps kubernetes-asyncio APIs for a single cluster.

    Exposes the five sub-clients Cocoa uses today (core / apps /
    networking / version / custom) plus convenience methods for the
    common operations Cocoa needs (deployment scale, restart, env;
    pod listing; namespace ensure; service/ingress/PVC reads).
    Watch + streaming APIs are inherited from
    :class:`K8sClientWatchMixin`.
    """

    def __init__(self, api_client: k8s_client.ApiClient):
        self._api = api_client
        self.core = k8s_client.CoreV1Api(api_client)
        self.apps = k8s_client.AppsV1Api(api_client)
        self.networking = k8s_client.NetworkingV1Api(api_client)
        self.version_api = k8s_client.VersionApi(api_client)
        self.custom = k8s_client.CustomObjectsApi(api_client)

    # ── Cluster-level ─────────────────────────────────
    async def test_connection(self) -> dict:
        info = await self.version_api.get_code()
        return {"version": info.git_version, "platform": info.platform}

    async def list_namespaces(self) -> list[str]:
        ns_list = await self.core.list_namespace()
        return [ns.metadata.name for ns in ns_list.items]

    async def ensure_namespace(
        self, name: str, extra_labels: dict[str, str] | None = None
    ) -> None:
        labels: dict[str, str] = {"app.kubernetes.io/managed-by": "cocoa"}
        if extra_labels:
            labels.update(extra_labels)
        try:
            await self.core.read_namespace(name)
        except k8s_client.ApiException as exc:
            if exc.status != 404:
                raise
            body = k8s_client.V1Namespace(
                metadata=k8s_client.V1ObjectMeta(name=name, labels=labels)
            )
            await self.core.create_namespace(body)

    # ── Deployment ────────────────────────────────────
    async def get_deployment(self, ns: str, name: str):
        return await self.apps.read_namespaced_deployment(name, ns)

    async def get_deployment_status(self, ns: str, name: str) -> dict:
        # Prefer full Deployment GET (covered by deployments get RBAC) over the
        # deployments/status subresource, which needs an explicit rule.
        dep = await self.apps.read_namespaced_deployment(name, ns)
        status = dep.status
        return {
            "replicas": status.replicas or 0,
            "ready_replicas": status.ready_replicas or 0,
            "updated_replicas": status.updated_replicas or 0,
            "available_replicas": status.available_replicas or 0,
            "conditions": [
                {"type": c.type, "status": c.status, "message": c.message}
                for c in (status.conditions or [])
            ],
        }

    async def scale_deployment(self, ns: str, name: str, replicas: int) -> None:
        body: dict = {"spec": {"replicas": replicas}}
        await self.apps.patch_namespaced_deployment_scale(name, ns, body)

    async def restart_deployment(self, ns: str, name: str) -> None:
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "cocoa/restartedAt": datetime.now(timezone.utc).isoformat()
                        }
                    }
                }
            }
        }
        await self.apps.patch_namespaced_deployment(name, ns, body)

    async def update_deployment_image(
        self, ns: str, name: str, image: str
    ) -> None:
        body = {
            "spec": {
                "template": {
                    "spec": {"containers": [{"name": name, "image": image}]}
                }
            }
        }
        await self.apps.patch_namespaced_deployment(name, ns, body)

    async def set_deployment_env(
        self,
        ns: str,
        name: str,
        container_name: str,
        key: str,
        value: str,
    ) -> None:
        body = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": container_name,
                                "env": [{"name": key, "value": value}],
                            }
                        ]
                    }
                }
            }
        }
        await self.apps.patch_namespaced_deployment(name, ns, body)

    # ── Pod ───────────────────────────────────────────
    async def list_pods(
        self, ns: str, label_selector: str = ""
    ) -> list[dict]:
        resp = await self.core.list_namespaced_pod(ns, label_selector=label_selector)
        results: list[dict] = []
        for pod in resp.items:
            containers = [
                {
                    "name": cs.name,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                }
                for cs in (pod.status.container_statuses or [])
            ]
            created = (
                pod.metadata.creation_timestamp.isoformat()
                if pod.metadata.creation_timestamp
                else None
            )
            results.append({
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "node": pod.spec.node_name,
                "ip": pod.status.pod_ip,
                "containers": containers,
                "created_at": created,
            })
        return results

    async def get_pod_logs(
        self,
        ns: str,
        pod: str,
        container: str | None = None,
        tail_lines: int = 200,
    ) -> str:
        return await self.core.read_namespaced_pod_log(
            pod, ns, container=container, tail_lines=tail_lines
        )

    # ── Service / Ingress ─────────────────────────────
    async def get_service(self, ns: str, name: str):
        return await self.core.read_namespaced_service(name, ns)

    async def get_ingress(self, ns: str, name: str):
        return await self.networking.read_namespaced_ingress(name, ns)

    # ── PVC / PV ──────────────────────────────────────
    async def read_pvc(self, ns: str, name: str):
        return await self.core.read_namespaced_persistent_volume_claim(name, ns)

    async def read_pv(self, name: str):
        return await self.core.read_persistent_volume(name)

    # ── Helpers ───────────────────────────────────────
    async def create_or_skip(self, create_fn, *args, **kwargs):
        """Call ``create_fn``; swallow 409 Conflict as a no-op."""
        try:
            return await create_fn(*args, **kwargs)
        except k8s_client.ApiException as exc:
            if exc.status != 409:
                raise
            logger.info("Resource already exists, skipping.")

    async def apply(self, create_fn, patch_fn, ns: str, name: str, body):
        """Create-or-update (idempotent). 409 from create falls back to patch."""
        try:
            return await create_fn(ns, body)
        except k8s_client.ApiException as exc:
            if exc.status != 409:
                raise
            return await patch_fn(name, ns, body)
