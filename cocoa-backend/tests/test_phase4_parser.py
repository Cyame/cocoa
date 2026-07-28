"""Unit tests for P4 slash parser — parse_directive and parse_turn.

Pure parser tests — no HTTP, no DB.  Validates structural syntax only.
"""

from app.core.slash_parser import parse_directive, parse_turn
from app.schemas.slash import Directive, Turn


class TestParseDirective:
    """parse_directive() — single-line parsing."""

    def test_parse_simple_directive(self) -> None:
        """A bare /cmd returns a Directive with no target or content-ref."""
        result = parse_directive("/read")
        assert isinstance(result, Directive)
        assert result.cmd == "/read"
        assert result.target_employee is None
        assert result.args == []
        assert result.content_ref is None

    def test_parse_targeted_directive(self) -> None:
        """@target before /cmd sets target_employee."""
        result = parse_directive("@reviewer /review")
        assert isinstance(result, Directive)
        assert result.cmd == "/review"
        assert result.target_employee == "reviewer"
        assert result.args == []
        assert result.content_ref is None

    def test_parse_content_ref(self) -> None:
        """A @scope:path content-ref is parsed into content_ref."""
        result = parse_directive("/read @fornix:docs/spec.md")
        assert isinstance(result, Directive)
        assert result.cmd == "/read"
        assert result.content_ref is not None
        assert result.content_ref.scope == "fornix"
        assert result.content_ref.path == "docs/spec.md"

    def test_parse_targeted_with_content_ref(self) -> None:
        """@target /cmd @scope:path — all fields populated."""
        result = parse_directive("@reviewer /review @fornix:docs/draft.md")
        assert isinstance(result, Directive)
        assert result.target_employee == "reviewer"
        assert result.cmd == "/review"
        assert result.content_ref is not None
        assert result.content_ref.scope == "fornix"
        assert result.content_ref.path == "docs/draft.md"
        assert result.raw_text == "@reviewer /review @fornix:docs/draft.md"

    def test_parse_memory_scope(self) -> None:
        """@memory is a valid content-ref scope."""
        result = parse_directive("/write @memory:lesson:intro")
        assert isinstance(result, Directive)
        assert result.cmd == "/write"
        assert result.content_ref is not None
        assert result.content_ref.scope == "memory"
        assert result.content_ref.path == "lesson:intro"

    def test_parse_invalid_line_to_general_text(self) -> None:
        """A line without /cmd returns the original string, not a Directive."""
        result = parse_directive("hello world")
        assert isinstance(result, str)
        assert result == "hello world"


class TestParseTurn:
    """parse_turn() — multi-line parsing."""

    def test_parse_empty_turn(self) -> None:
        """Empty input returns a Turn with no directives and no general text."""
        result = parse_turn("")
        assert isinstance(result, Turn)
        assert result.directives == []
        assert result.general_text is None

    def test_parse_multi_directive_turn(self) -> None:
        """Multi-line input with two /cmd lines produces two directives."""
        result = parse_turn("@mi-shi /plan\n/review")
        assert isinstance(result, Turn)
        assert len(result.directives) == 2
        assert result.directives[0].target_employee == "mi-shi"
        assert result.directives[0].cmd == "/plan"
        assert result.directives[1].target_employee is None
        assert result.directives[1].cmd == "/review"
        assert result.general_text is None
