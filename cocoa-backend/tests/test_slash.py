"""Tests for app.schemas.slash — pure Pydantic validation, no DB required."""

import pytest
from pydantic import ValidationError

from app.schemas.slash import CommandRegistry, ContentRef, Directive, Turn


class TestContentRef:
    """Validation tests for ContentRef."""

    def test_scope_none_raises_validation_error(self) -> None:
        """scope=None must be rejected."""
        with pytest.raises(ValidationError):
            ContentRef(scope=None)

    def test_scope_missing_raises_validation_error(self) -> None:
        """Omitting scope must be rejected (field has no default)."""
        with pytest.raises(ValidationError):
            ContentRef()  # type: ignore[call-arg]

    def test_scope_workspace_with_path(self) -> None:
        """Valid scope + path combination."""
        ref = ContentRef(scope="workspace", path="/foo")
        assert ref.scope == "workspace"
        assert ref.path == "/foo"

    def test_scope_blackboard_no_path(self) -> None:
        """Valid scope without path (path defaults to None)."""
        ref = ContentRef(scope="blackboard")
        assert ref.scope == "blackboard"
        assert ref.path is None

    def test_invalid_scope_value_raises_validation_error(self) -> None:
        """A scope outside the Literal must be rejected."""
        with pytest.raises(ValidationError):
            ContentRef(scope="invalid_scope")


class TestDirective:
    """Validation tests for Directive."""

    def test_cmd_read_validates(self) -> None:
        """Minimal valid directive."""
        d = Directive(cmd="/read")
        assert d.cmd == "/read"
        assert d.args == []
        assert d.target_employee is None
        assert d.content_ref is None
        assert d.raw_text == ""

    def test_cmd_missing_raises_validation_error(self) -> None:
        """cmd is required with no default."""
        with pytest.raises(ValidationError):
            Directive()  # type: ignore[call-arg]

    def test_full_directive_with_content_ref(self) -> None:
        """Directive with all optional fields populated."""
        ref = ContentRef(scope="memory", path="notes/meeting")
        d = Directive(
            target_employee="alice",
            cmd="/write",
            args=["summary", "draft"],
            content_ref=ref,
            raw_text="@alice /write summary draft ->memory",
        )
        assert d.target_employee == "alice"
        assert d.cmd == "/write"
        assert d.args == ["summary", "draft"]
        assert d.content_ref == ref
        assert d.raw_text == "@alice /write summary draft ->memory"


class TestTurn:
    """Validation tests for Turn."""

    def test_empty_directives_default(self) -> None:
        """Turn with no args defaults to empty directives."""
        t = Turn()
        assert t.directives == []
        assert t.general_text is None

    def test_two_directives(self) -> None:
        """Turn with two directives validates correctly."""
        t = Turn(
            directives=[
                Directive(cmd="/read"),
                Directive(cmd="/write", args=["file.md"]),
            ]
        )
        assert len(t.directives) == 2
        assert t.directives[0].cmd == "/read"
        assert t.directives[1].args == ["file.md"]


class TestCommandRegistry:
    """Validation tests for CommandRegistry."""

    def test_global_commands(self) -> None:
        """CommandRegistry with two global commands."""
        cr = CommandRegistry(global_commands=["/read", "/list"])
        assert cr.global_commands == ["/read", "/list"]

    def test_preset_commands(self) -> None:
        """CommandRegistry with preset command overrides."""
        cr = CommandRegistry(
            global_commands=["/read"],
            preset_commands={"coder": ["/read", "/write", "/execute"]},
        )
        assert cr.global_commands == ["/read"]
        assert cr.preset_commands == {"coder": ["/read", "/write", "/execute"]}

    def test_empty_registry(self) -> None:
        """CommandRegistry defaults to empty."""
        cr = CommandRegistry()
        assert cr.global_commands == []
        assert cr.preset_commands == {}
