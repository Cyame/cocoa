"""Unit tests for ``app.services.k8s.resource_builder`` (P11b).

The builders are pure dataclass constructors — no K8s API calls — so
the three tests inspect the returned ``V1*`` object graph directly.

Covers the three must-have surfaces:

* ``build_labels`` produces the required K8s-recommended keys
* ``build_deployment`` threads ``env_vars`` and resource limits
* ``build_network_policy`` translates ``ingress_from_pod_labels`` into
  the typed ``V1NetworkPolicyIngressRule`` shape
"""

from kubernetes_asyncio.client import V1Deployment, V1NetworkPolicy

from app.services.k8s.resource_builder import (
    build_deployment,
    build_labels,
    build_network_policy,
)

# ── 1. build_labels returns the required K8s-recommended keys ──


def test_build_labels_returns_dict_with_required_keys() -> None:
    """``build_labels("inst-1", "v1.0")`` carries every required K8s key."""
    labels = build_labels("inst-1", "v1.0")

    assert labels["app.kubernetes.io/name"] == "inst-1"
    assert labels["app.kubernetes.io/managed-by"] == "cocoa"
    assert labels["cocoa/instance-id"] == "inst-1"
    assert labels["cocoa/image-tag"] == "v1.0"


# ── 2. build_deployment threads env_vars + resources ─────────────


def test_build_deployment_includes_env_vars_and_resources() -> None:
    """``build_deployment(..., env_vars={"FOO": "bar"})`` propagates env + limits."""
    deployment = build_deployment(
        "d1",
        "default",
        "img:latest",
        env_vars={"FOO": "bar"},
    )

    assert isinstance(deployment, V1Deployment)
    container = deployment.spec.template.spec.containers[0]
    assert container.env is not None and len(container.env) == 1
    assert container.env[0].name == "FOO"
    assert container.env[0].value == "bar"
    assert container.resources.requests == {"cpu": "100m", "memory": "256Mi"}
    assert container.resources.limits == {"cpu": "500m", "memory": "1Gi"}


# ── 3. build_network_policy translates ingress_from_pod_labels ──


def test_build_network_policy_with_ingress_from_pods() -> None:
    """Ingress rule narrows source peers to pods matching ``app=backend``."""
    policy = build_network_policy(
        "np1",
        "default",
        {"app": "cocoa"},
        {"app": "backend"},
    )

    assert isinstance(policy, V1NetworkPolicy)
    assert policy.spec.pod_selector.match_labels == {"app": "cocoa"}
    assert policy.spec.policy_types == ["Ingress"]

    rules = policy.spec.ingress
    assert rules is not None and len(rules) == 1
    peers = rules[0]._from
    assert peers is not None and len(peers) == 1
    assert peers[0].pod_selector.match_labels == {"app": "backend"}
