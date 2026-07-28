"""Tests for the directory path contract (``app.core.dirs``)."""

import pytest

from app.core.dirs import (
    fornix_dir,
    employee_dir,
    memory_export_path,
    vault_dir,
    workspace_dir,
)


class TestEmployeeDir:
    def test_returns_relative_path(self) -> None:
        assert employee_dir("analyst") == ".pi/analyst/"

    def test_trailing_slash(self) -> None:
        assert employee_dir("researcher").endswith("/")

    def test_rejects_parent_traversal(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            employee_dir("..")
        with pytest.raises(ValueError, match="Path traversal"):
            employee_dir("foo/../bar")

    def test_rejects_leading_dotslash_traversal(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            employee_dir("../etc")


class TestWorkspaceDir:
    def test_returns_relative_path(self) -> None:
        assert workspace_dir("abc-123") == "workspace/abc-123/"

    def test_trailing_slash(self) -> None:
        assert workspace_dir("abc-123").endswith("/")

    def test_rejects_parent_traversal(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            workspace_dir("..")
        with pytest.raises(ValueError, match="Path traversal"):
            workspace_dir("instance/../../root")


class TestBlackboardDir:
    def test_returns_relative_path(self) -> None:
        assert fornix_dir("office-1") == "fornix/office-1/"

    def test_trailing_slash(self) -> None:
        assert fornix_dir("office-1").endswith("/")

    def test_rejects_parent_traversal(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            fornix_dir("..")
        with pytest.raises(ValueError, match="Path traversal"):
            fornix_dir("x/..")


class TestVaultDir:
    def test_returns_relative_path(self) -> None:
        assert vault_dir("office-2") == "vault/office-2/"

    def test_trailing_slash(self) -> None:
        assert vault_dir("office-2").endswith("/")

    def test_rejects_parent_traversal(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            vault_dir("..")
        with pytest.raises(ValueError, match="Path traversal"):
            vault_dir("./../oops")


class TestMemoryExportPath:
    def test_returns_relative_file_path(self) -> None:
        assert memory_export_path("analyst") == "memory/analyst.jsonl"

    def test_no_trailing_slash(self) -> None:
        result = memory_export_path("researcher")
        assert not result.endswith("/")
        assert result.endswith(".jsonl")

    def test_rejects_parent_traversal(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            memory_export_path("..")
        with pytest.raises(ValueError, match="Path traversal"):
            memory_export_path("../../../etc/passwd")

    def test_dot_single_component_passes(self) -> None:
        # "." alone is not traversal — it's a valid slug (though unlikely in practice).
        assert memory_export_path(".") == "memory/..jsonl"


class TestPathTraversalEdgeCases:
    """Cross-function: every function rejects ``..`` consistently."""

    @pytest.mark.parametrize("func,slug", [
        (employee_dir, ".."),
        (employee_dir, "a/../b"),
        (workspace_dir, ".."),
        (workspace_dir, "x/../y"),
        (fornix_dir, ".."),
        (fornix_dir, "a/.."),
        (vault_dir, ".."),
        (vault_dir, "../vault"),
        (memory_export_path, ".."),
        (memory_export_path, "worker/../root"),
    ])
    def test_rejects_dotdot(self, func, slug: str) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            func(slug)
