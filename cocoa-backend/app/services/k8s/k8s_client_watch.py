"""K8sClient watch/streaming extensions.

Split from k8s_client.py to keep that file under the 500 LOC ceiling.
"""

import logging
from typing import Any, AsyncIterator

from kubernetes_asyncio import watch

logger = logging.getLogger(__name__)


class K8sClientWatchMixin:
    """Watch + streaming methods for K8sClient.

    Used as a mixin: ``K8sClient(K8sClientWatchMixin)`` so all watch
    methods are accessible on the main client instance without forcing
    k8s_client.py to carry their LOC budget.
    """

    # ── Pod / Event watch ─────────────────────────────
    async def watch_pods(
        self,
        ns: str,
        label_selector: str = "",
        timeout_seconds: int = 1800,
    ) -> AsyncIterator[dict]:
        """Yield pod watch events as an async iterator."""
        w = watch.Watch()
        async for event in w.stream(
            self.core.list_namespaced_pod,
            ns,
            label_selector=label_selector,
            timeout_seconds=timeout_seconds,
        ):
            obj = event["object"]
            yield {
                "type": event["type"],
                "pod": obj.metadata.name,
                "phase": obj.status.phase,
            }

    async def watch_events(
        self, ns: str, timeout_seconds: int = 1800
    ) -> AsyncIterator[dict]:
        """Yield cluster Event watch events as an async iterator."""
        w = watch.Watch()
        async for event in w.stream(
            self.core.list_namespaced_event,
            ns,
            timeout_seconds=timeout_seconds,
        ):
            obj = event["object"]
            involved = obj.involved_object.name if obj.involved_object else None
            last_ts = obj.last_timestamp.isoformat() if obj.last_timestamp else None
            yield {
                "type": event["type"],
                "reason": obj.reason,
                "message": obj.message,
                "involved": involved,
                "count": obj.count,
                "last_timestamp": last_ts,
            }

    # ── Pod log streaming ────────────────────────────
    async def stream_pod_logs(
        self,
        ns: str,
        pod: str,
        container: str | None = None,
        tail_lines: int = 50,
        since_seconds: int | None = None,
        since_time: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield log lines as an async iterator with optional time range.

        Uses ``_preload_content=False`` so the HTTP body can be iterated
        as a stream of chunks instead of buffered into one string.
        """
        kwargs: dict = {"container": container, "follow": True, "_preload_content": False}
        if since_seconds is not None:
            kwargs["since_seconds"] = since_seconds
        elif since_time is not None:
            kwargs["since_time"] = since_time
        else:
            kwargs["tail_lines"] = tail_lines

        resp: Any = await self.core.read_namespaced_pod_log(pod, ns, **kwargs)
        async for line in resp.content:
            yield line.decode("utf-8", errors="replace").rstrip("\n")

    # ── Metrics ───────────────────────────────────────
    async def list_pod_metrics(self, ns: str) -> list[dict]:
        """Try to get pod metrics via metrics.k8s.io; empty list on failure.

        metrics-server is optional, so we swallow any error and return [].
        """
        try:
            data = await self.custom.list_namespaced_custom_object(
                "metrics.k8s.io", "v1beta1", ns, "pods"
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("metrics-server unavailable for ns=%s: %s", ns, exc)
            return []

        results: list[dict] = []
        for item in data.get("items", []):
            containers = item.get("containers", [])
            results.append({
                "name": item["metadata"]["name"],
                "cpu": sum(_parse_cpu(c.get("usage", {}).get("cpu", "0")) for c in containers),
                "memory": sum(_parse_memory(c.get("usage", {}).get("memory", "0")) for c in containers),
            })
        return results


# ── Quantity parsing utilities ──────────────────────────


def _parse_cpu(value: str) -> int:
    """Parse a K8s CPU Quantity string to millicores."""
    value = str(value).strip()
    if not value:
        return 0
    if value.endswith("n"):
        try:
            return int(value[:-1]) // 1_000_000
        except ValueError:
            return 0
    if value.endswith("m"):
        try:
            return int(value[:-1])
        except ValueError:
            return 0
    try:
        return int(float(value) * 1000)
    except ValueError:
        return 0


def _parse_memory(value: str) -> int:
    """Parse a K8s memory Quantity string to whole MiB.

    Handles binary suffixes (Ki/Mi/Gi/Ti), decimal suffixes (K/M/G/T),
    plain bytes, and millibytes (m).
    """
    value = str(value).strip()
    if not value or value == "0":
        return 0
    if value.endswith("Ki"):
        try:
            return int(value[:-2]) // 1024
        except ValueError:
            return 0
    if value.endswith("Mi"):
        try:
            return int(value[:-2])
        except ValueError:
            return 0
    if value.endswith("Gi"):
        try:
            return int(float(value[:-2]) * 1024)
        except ValueError:
            return 0
    if value.endswith("Ti"):
        try:
            return int(float(value[:-2]) * 1024 * 1024)
        except ValueError:
            return 0
    if value.endswith("m"):
        try:
            milli_bytes = int(value[:-1])
            return milli_bytes // 1000 // (1024 * 1024)
        except ValueError:
            return 0
    if value.endswith("G"):
        try:
            return int(float(value[:-1]) * 1_000_000_000 / (1024 * 1024))
        except ValueError:
            return 0
    if value.endswith("M"):
        try:
            return int(float(value[:-1]) * 1_000_000 / (1024 * 1024))
        except ValueError:
            return 0
    if value.endswith("K") or value.endswith("k"):
        try:
            return int(float(value[:-1]) * 1000 / (1024 * 1024))
        except ValueError:
            return 0
    if value.endswith("T"):
        try:
            return int(float(value[:-1]) * 1_000_000_000_000 / (1024 * 1024))
        except ValueError:
            return 0
    try:
        return int(float(value)) // (1024 * 1024)
    except (ValueError, OverflowError):
        logger.warning("Failed to parse memory value: %s", value)
        return 0
