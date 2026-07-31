"""ResourceBuilder: programmatic K8s manifest construction for Cocoa instances.

Each ``build_*`` function returns a typed ``V1*`` object from
``kubernetes_asyncio.client``. Functions never call the K8s API — they
only construct the manifest dataclasses, leaving creation / apply to
``K8sClient.create_or_skip`` (P11a).

P11b scope: 7 essential builders (``build_labels`` + 6 ``build_*`` of
workload-style resources + ``build_service``). Higher-level ingress /
proxy builders are deferred to P12.
"""

import os

from kubernetes_asyncio.client import (
    V1ConfigMap,
    V1ConfigMapVolumeSource,
    V1Container,
    V1ContainerPort,
    V1Deployment,
    V1DeploymentSpec,
    V1EnvFromSource,
    V1EnvVar,
    V1HostPathVolumeSource,
    V1LabelSelector,
    V1NetworkPolicy,
    V1NetworkPolicyIngressRule,
    V1NetworkPolicyPeer,
    V1NetworkPolicySpec,
    V1ObjectMeta,
    V1PersistentVolumeClaim,
    V1PersistentVolumeClaimSpec,
    V1PersistentVolumeClaimVolumeSource,
    V1PodSpec,
    V1PodTemplateSpec,
    V1ResourceQuota,
    V1ResourceQuotaSpec,
    V1ResourceRequirements,
    V1Secret,
    V1SecretEnvSource,
    V1Service,
    V1ServicePort,
    V1ServiceSpec,
    V1Volume,
    V1VolumeMount,
    V1VolumeResourceRequirements,
)

# Label keys — kept as constants so callers (and tests) share one source of truth.
LABEL_NAME = "app.kubernetes.io/name"
LABEL_MANAGED_BY = "app.kubernetes.io/managed-by"
LABEL_INSTANCE_ID = "cocoa/instance-id"
LABEL_IMAGE_TAG = "cocoa/image-tag"

MANAGED_BY = "cocoa"

# Volume / mount constants — referenced by build_deployment and (eventually)
# by callers that want to mount additional PVCs.
CONFIG_VOLUME_NAME = "config"
CONFIG_MOUNT_PATH = "/etc/config"
DATA_VOLUME_NAME = "data"
DATA_MOUNT_PATH = "/data"
SHARED_VOLUME_NAME = "shared"
SHARED_MOUNT_PATH = "/data/shared"


def build_labels(instance_id: str, image_tag: str = "") -> dict[str, str]:
    """Build the standard label set applied to every Cocoa-owned resource.

    Required keys (always present):

    * ``app.kubernetes.io/name`` — K8s recommended app identifier
    * ``app.kubernetes.io/managed-by`` — always ``"cocoa"``
    * ``cocoa/instance-id`` — links the resource back to a Cocoa instance

    Optional:

    * ``cocoa/image-tag`` — included only when ``image_tag`` is non-empty
    """
    labels: dict[str, str] = {
        LABEL_NAME: instance_id,
        LABEL_MANAGED_BY: MANAGED_BY,
        LABEL_INSTANCE_ID: instance_id,
    }
    if image_tag:
        labels[LABEL_IMAGE_TAG] = image_tag
    return labels


def build_configmap(
    name: str,
    ns: str,
    data: dict[str, str],
    labels: dict[str, str] | None = None,
) -> V1ConfigMap:
    """Build a ConfigMap from a string→string mapping.

    ``data`` is stored verbatim (no base64); callers pass plain text.
    """
    return V1ConfigMap(
        metadata=V1ObjectMeta(name=name, namespace=ns, labels=labels or {}),
        data=data,
    )


def build_env_secret(
    name: str,
    ns: str,
    env_vars: dict[str, str],
    labels: dict[str, str] | None = None,
) -> V1Secret:
    """Build an Opaque Secret that holds key=value environment variables.

    Uses ``string_data`` (Kubernetes writes base64 on apply). Callers pass
    plain text; the API server encodes.
    """
    return V1Secret(
        metadata=V1ObjectMeta(name=name, namespace=ns, labels=labels or {}),
        type="Opaque",
        string_data=env_vars,
    )


def build_pvc(
    name: str,
    ns: str,
    storage_size: str = "1Gi",
    labels: dict[str, str] | None = None,
) -> V1PersistentVolumeClaim:
    """Build a single-volume PVC with ``ReadWriteOnce`` access mode."""
    return V1PersistentVolumeClaim(
        metadata=V1ObjectMeta(name=name, namespace=ns, labels=labels or {}),
        spec=V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            resources=V1VolumeResourceRequirements(requests={"storage": storage_size}),
        ),
    )


def build_resource_quota(
    ns: str,
    cpu: str = "2",
    mem: str = "4Gi",
    name: str | None = None,
) -> V1ResourceQuota:
    """Build a namespace-level ResourceQuota bounding CPU + memory + pod count.

    ``name`` defaults to ``"cocoa-quota"`` when omitted so callers can
    reference the same quota across multiple calls.
    """
    return V1ResourceQuota(
        metadata=V1ObjectMeta(name=name or "cocoa-quota", namespace=ns),
        spec=V1ResourceQuotaSpec(
            hard={
                "requests.cpu": cpu,
                "requests.memory": mem,
                "limits.cpu": cpu,
                "limits.memory": mem,
                "pods": "20",
            },
        ),
    )


def build_deployment(
    name: str,
    ns: str,
    image: str,
    replicas: int = 1,
    labels: dict[str, str] | None = None,
    configmap_name: str | None = None,
    secret_name: str | None = None,
    pvc_name: str | None = None,
    shared_host_path: str | None = None,
    cpu_request: str = "100m",
    cpu_limit: str = "500m",
    mem_request: str = "256Mi",
    mem_limit: str = "1Gi",
    port: int = 8080,
    env_vars: dict[str, str] | None = None,
) -> V1Deployment:
    """Build a Deployment for one instance container.

    Optional integrations (each independently switchable):

    * ``configmap_name`` — mount the configmap at ``/etc/config``
    * ``secret_name`` — project secret keys as env vars (``envFrom``)
    * ``pvc_name`` — mount the PVC at ``/data``
    * ``shared_host_path`` — hostPath mounted at ``/data/shared`` (orbstack /
      single-node; production should use RWX PVC instead)
    * ``env_vars`` — additional literal env vars (``FOO=bar``)

    The container always gets a ``container_port`` and CPU/memory
    requests + limits. Resource values are required by the namespace's
    ResourceQuota (P11a convention).
    """
    selector_labels = labels or {}
    container = V1Container(
        name=name[:63],
        image=image,
        image_pull_policy=os.environ.get("COCOA_INSTANCE_IMAGE_PULL_POLICY", "IfNotPresent"),
        ports=[V1ContainerPort(container_port=port)],
        resources=V1ResourceRequirements(
            requests={"cpu": cpu_request, "memory": mem_request},
            limits={"cpu": cpu_limit, "memory": mem_limit},
        ),
    )

    if env_vars:
        container.env = [V1EnvVar(name=k, value=v) for k, v in env_vars.items()]

    volumes: list[V1Volume] = []
    volume_mounts: list[V1VolumeMount] = []

    if configmap_name:
        volumes.append(
            V1Volume(
                name=CONFIG_VOLUME_NAME,
                config_map=V1ConfigMapVolumeSource(name=configmap_name),
            ),
        )
        volume_mounts.append(
            V1VolumeMount(name=CONFIG_VOLUME_NAME, mount_path=CONFIG_MOUNT_PATH),
        )

    if secret_name:
        container.env_from = [
            V1EnvFromSource(secret_ref=V1SecretEnvSource(name=secret_name)),
        ]

    if pvc_name:
        volumes.append(
            V1Volume(
                name=DATA_VOLUME_NAME,
                persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
                    claim_name=pvc_name,
                ),
            ),
        )
        volume_mounts.append(
            V1VolumeMount(name=DATA_VOLUME_NAME, mount_path=DATA_MOUNT_PATH),
        )

    if shared_host_path:
        volumes.append(
            V1Volume(
                name=SHARED_VOLUME_NAME,
                host_path=V1HostPathVolumeSource(
                    path=shared_host_path,
                    type="DirectoryOrCreate",
                ),
            ),
        )
        volume_mounts.append(
            V1VolumeMount(name=SHARED_VOLUME_NAME, mount_path=SHARED_MOUNT_PATH),
        )

    if volume_mounts:
        container.volume_mounts = volume_mounts

    return V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=V1ObjectMeta(name=name, namespace=ns, labels=selector_labels),
        spec=V1DeploymentSpec(
            replicas=replicas,
            selector=V1LabelSelector(match_labels=selector_labels),
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(labels=selector_labels),
                spec=V1PodSpec(containers=[container], volumes=volumes or None),
            ),
        ),
    )


def build_network_policy(
    name: str,
    ns: str,
    pod_labels: dict[str, str],
    ingress_from_pod_labels: dict[str, str] | None = None,
) -> V1NetworkPolicy:
    """Build a NetworkPolicy restricting ingress to a labeled set of pods.

    ``pod_labels`` selects which pods this policy applies to. The
    ``ingress`` rule is optional — when ``ingress_from_pod_labels`` is
    provided, only pods carrying those labels may reach the selected
    pods. When omitted, ``ingress`` is left unset (default-deny on the
    selected pods).
    """
    spec = V1NetworkPolicySpec(
        pod_selector=V1LabelSelector(match_labels=pod_labels),
        policy_types=["Ingress"],
    )
    if ingress_from_pod_labels:
        spec.ingress = [
            V1NetworkPolicyIngressRule(
                _from=[
                    V1NetworkPolicyPeer(
                        pod_selector=V1LabelSelector(
                            match_labels=ingress_from_pod_labels,
                        ),
                    ),
                ],
            ),
        ]
    return V1NetworkPolicy(
        api_version="networking.k8s.io/v1",
        kind="NetworkPolicy",
        metadata=V1ObjectMeta(name=name, namespace=ns, labels=pod_labels),
        spec=spec,
    )


def build_service(
    name: str,
    ns: str,
    port: int = 80,
    target_port: int = 8080,
    labels: dict[str, str] | None = None,
) -> V1Service:
    """Build a ClusterIP Service fronting a Deployment's container port.

    ``port`` is the in-cluster Service port; ``target_port`` maps to the
    container's listening port. ``labels`` is used both for the Service
    metadata and as the pod selector (must match the Deployment's pod
    template labels).
    """
    selector = labels or {}
    return V1Service(
        metadata=V1ObjectMeta(name=name, namespace=ns, labels=selector),
        spec=V1ServiceSpec(
            selector=selector,
            ports=[
                V1ServicePort(port=port, target_port=target_port, protocol="TCP"),
            ],
            type="ClusterIP",
        ),
    )
