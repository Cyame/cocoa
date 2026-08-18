"""Regression tests for tracked Kubernetes manifests."""

from pathlib import Path

import yaml


def test_eyot_portal_uses_the_non_legacy_node_port() -> None:
    """The Eyot portal must not collide with the legacy Cocoa Service."""
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "eyot-artifacts"
        / "k8s"
        / "portal-deployment.yaml"
    )
    documents = list(yaml.safe_load_all(manifest_path.read_text()))
    service = next(
        document
        for document in documents
        if document.get("kind") == "Service"
        and document.get("metadata", {}).get("name") == "eyot-portal"
    )

    assert service["spec"]["type"] == "NodePort"
    assert service["spec"]["ports"][0]["nodePort"] == 30174


def test_portal_acceptance_scripts_use_the_non_legacy_node_port() -> None:
    """Acceptance scripts must target the same port as the tracked manifest."""
    repository_root = Path(__file__).resolve().parents[2]
    scripts = (
        repository_root / "scripts" / "v4-9-2-acceptance.sh",
        repository_root / "scripts" / "v4-9-3-acceptance.sh",
    )

    for script in scripts:
        content = script.read_text()
        assert "30174" in content
        assert "30173" not in content
