"""Tests for DistillationEngine Protocol and AggregatingDistiller heuristic.

Covers the 8 required QA scenarios from the P10 plan plus additional
edge cases (soft-delete exclusion, kind filter, commands cap, etc.).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.distillation import (
    AggregatingDistiller,
    DistillationEngine,
    DistillationError,
    DistillResult,
)
from app.models.employee import EmployeePreset
from app.models.memory import MemoryEntry, MemoryKind
from app.schemas.learning import AggregatedMemoryCount, DistillRequest, SkillManifestPreview


# ---------------------------------------------------------------------------
# Protocol / Error / Dataclass structural tests
# ---------------------------------------------------------------------------


class TestDistillationEngineProtocol:
    """Verify the DistillationEngine Protocol is importable and structured."""

    def test_protocol_importable(self) -> None:
        """DistillationEngine must be importable."""
        assert DistillationEngine is not None

    def test_distill_is_protocol_method(self) -> None:
        """The distill method must be part of the Protocol's interface."""
        assert hasattr(DistillationEngine, "distill")


class TestDistillationError:
    """Verify DistillationError carries structured error fields."""

    def test_error_fields(self) -> None:
        """DistillationError must store code, message_key, message."""
        err = DistillationError(
            code="test.code",
            message_key="errors.test.code",
            message="A test error occurred",
        )
        assert err.code == "test.code"
        assert err.message_key == "errors.test.code"
        assert err.message == "A test error occurred"

    def test_is_exception(self) -> None:
        """DistillationError must be an Exception subclass."""
        assert issubclass(DistillationError, Exception)


class TestDistillResult:
    """Verify DistillResult dataclass."""
    
    def test_fields_present(self) -> None:
        """DistillResult must have all 5 fields."""
        preview = SkillManifestPreview()
        counts = AggregatedMemoryCount()
        dr = DistillResult(
            new_preset_slug="slug",
            manifest_preview=preview,
            aggregated_memory=counts,
            source_employee_id="eid",
            source_preset_slug=None,
        )
        assert dr.new_preset_slug == "slug"
        assert dr.manifest_preview is preview
        assert dr.aggregated_memory is counts
        assert dr.source_employee_id == "eid"
        assert dr.source_preset_slug is None


# ---------------------------------------------------------------------------
# AggregatingDistiller integration tests
# ---------------------------------------------------------------------------


class TestAggregatingDistiller:
    """Integration tests for AggregatingDistiller.distill().

    Each test uses the per-test ``session`` fixture, which provides an
    isolated database with Alembic-migrated schema.
    """

    # -- Helper --------------------------------------------------------------

    async def _add_entries(
        self,
        session: AsyncSession,
        employee_id: str,
        *specs: tuple[str, str | None, str | None],
    ) -> None:
        """Insert memory entries. Each spec is (kind, key, content)."""
        for kind, key, content in specs:
            session.add(
                MemoryEntry(
                    employee_id=employee_id,
                    kind=kind,
                    key=key,
                    content=content,
                )
            )
        await session.flush()

    # -- Tests ---------------------------------------------------------------

    async def test_empty_memory_raises_distillation_error(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """When employee has no memory entries, distill raises DistillationError."""
        emp = await employee_factory()
        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")

        with pytest.raises(DistillationError) as exc_info:
            await distiller.distill(emp.id, request=request, session=session)
        assert exc_info.value.code == "learning.no_memory"

    async def test_employee_not_found_raises_error(self, session: AsyncSession) -> None:
        """When employee does not exist, distill raises DistillationError."""
        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")

        with pytest.raises(DistillationError) as exc_info:
            await distiller.distill("nonexistent-id", request=request, session=session)
        assert exc_info.value.code == "employee.not_found"

    async def test_mixed_kinds_correct_counts(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """Memory entries of all 4 kinds produce correct aggregated counts."""
        emp = await employee_factory()
        specs: list[tuple[str, str | None, str | None]] = []
        for kind in MemoryKind:
            for i in range(3):
                specs.append((kind.value, f"{kind.value}-{i}", f"Content {kind.value} {i}"))
        await self._add_entries(session, emp.id, *specs)

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.aggregated_memory.experience == 3
        assert result.aggregated_memory.lesson == 3
        assert result.aggregated_memory.decision == 3
        assert result.aggregated_memory.problem == 3
        assert result.aggregated_memory.total == 12

    async def test_kind_filter_respects_filter(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """When kind filter is specified, only those kinds are aggregated."""
        emp = await employee_factory()
        await self._add_entries(
            session,
            emp.id,
            ("experience", "exp-1", None),
            ("lesson", "learn-1", None),
            ("decision", "dec-1", None),
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(
            target_skill_slug="test-skill",
            memory_kind_filter=["experience", "lesson"],
        )
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.aggregated_memory.experience == 1
        assert result.aggregated_memory.lesson == 1
        assert result.aggregated_memory.decision == 0
        assert result.aggregated_memory.total == 2

    async def test_lesson_keys_extract_kebab_case_to_commands(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """Kebab-case keys from lesson/decision entries become commands."""
        emp = await employee_factory()
        await self._add_entries(
            session,
            emp.id,
            ("lesson", "debug-concurrency", "Debug concurrency issues"),
            ("decision", "rollback-migration", "Decision to rollback"),
            ("experience", "something-else", "Not a command source"),
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        assert "debug-concurrency" in result.manifest_preview.commands
        assert "rollback-migration" in result.manifest_preview.commands
        # experience entries must NOT contribute to commands
        assert "something-else" not in result.manifest_preview.commands

    async def test_commands_max_ten(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """Commands list must not exceed 10 entries."""
        emp = await employee_factory()
        specs: list[tuple[str, str | None, str | None]] = []
        for i in range(15):
            specs.append(("lesson", f"cmd-{i:02d}", "..."))
        await self._add_entries(session, emp.id, *specs)

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        assert len(result.manifest_preview.commands) <= 10

    async def test_non_kebab_keys_excluded_from_commands(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """Keys that don't match the kebab-case pattern must not appear in commands."""
        emp = await employee_factory()
        await self._add_entries(
            session,
            emp.id,
            ("lesson", "Valid-Key", "Mixed case key"),       # uppercase → no match
            ("lesson", "1-starting-digit", "Num start"),       # starts with digit → no match
            ("experience", "ok-key", "valid filler"),          # for non-empty check
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        assert "Valid-Key" not in result.manifest_preview.commands
        assert "1-starting-digit" not in result.manifest_preview.commands

    async def test_longest_lesson_content_truncated_to_200_chars(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """Longest lesson content (>= 50 chars) truncated to 200 chars + '...'."""
        emp = await employee_factory()
        long_content = "x" * 210  # 210 chars — triggers truncation
        await self._add_entries(
            session,
            emp.id,
            ("lesson", "long-lesson", long_content),
            ("lesson", "short-lesson", "Short content"),       # shorter, should be ignored
            ("experience", "exp-1", "filler"),                 # ensures non-empty
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        # 200 chars + "..." = 203
        assert len(result.manifest_preview.prompt) == 203
        assert result.manifest_preview.prompt.endswith("...")
        assert result.manifest_preview.prompt.startswith("x" * 200)

    async def test_lesson_content_under_50_chars_falls_back_to_default(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """When no lesson content >= 50 chars, prompt defaults to 'TODO P8'."""
        emp = await employee_factory()
        await self._add_entries(
            session,
            emp.id,
            ("lesson", "short", "Too short"),
            ("experience", "exp-1", "filler"),
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.manifest_preview.prompt == "TODO P8"

    async def test_key_prefix_deduplication_to_skills(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """First segment of each key (split on '-') deduplicated into skills."""
        emp = await employee_factory()
        await self._add_entries(
            session,
            emp.id,
            ("experience", "debug-concurrency", "..."),
            ("lesson", "debug-memory-leak", "..."),
            ("decision", "deploy-rollback", "..."),
            ("problem", "network-timeout", "..."),
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        skills = result.manifest_preview.skills
        assert "debug" in skills
        assert "deploy" in skills
        assert "network" in skills
        # "debug" must appear only once
        assert skills.count("debug") == 1

    async def test_source_preset_none_model_defaults_to_tbd(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """When source_preset_slug is None, model defaults to 'tbd'."""
        emp = await employee_factory()
        await self._add_entries(session, emp.id, ("experience", "test-key", "Test content"))

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill", source_preset_slug=None)
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.manifest_preview.model == "tbd"

    async def test_source_preset_exists_model_inherits(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """When source preset exists, model inherits from manifest['model']."""
        emp = await employee_factory()
        session.add(EmployeePreset(
            slug="source-preset",
            name="Source Preset",
            manifest={"model": "gpt-4o", "prompt": "You are helpful."},
        ))
        await self._add_entries(session, emp.id, ("experience", "test-key", "Test content"))
        await session.flush()

        distiller = AggregatingDistiller()
        request = DistillRequest(
            target_skill_slug="test-skill",
            source_preset_slug="source-preset",
        )
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.manifest_preview.model == "gpt-4o"

    async def test_slug_generated_correctly(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """New preset slug follows {base}-skill-{target_skill_slug} pattern."""
        emp = await employee_factory()
        await self._add_entries(session, emp.id, ("experience", "test-key", "Test content"))

        distiller = AggregatingDistiller()

        # Without source_preset_slug → base = "base"
        request = DistillRequest(target_skill_slug="distributed-debugging")
        result = await distiller.distill(emp.id, request=request, session=session)
        assert result.new_preset_slug == "base-skill-distributed-debugging"
        assert result.source_preset_slug is None

        # With source_preset_slug
        request2 = DistillRequest(
            target_skill_slug="distributed-debugging",
            source_preset_slug="mi-shi",
        )
        result2 = await distiller.distill(emp.id, request=request2, session=session)
        assert result2.new_preset_slug == "mi-shi-skill-distributed-debugging"
        assert result2.source_preset_slug == "mi-shi"
        assert result2.source_employee_id == emp.id

    async def test_soft_deleted_entries_excluded(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """Soft-deleted memory entries must be excluded from aggregation."""
        emp = await employee_factory()
        active = MemoryEntry(employee_id=emp.id, kind="experience", key="active-key", content="Active")
        deleted = MemoryEntry(employee_id=emp.id, kind="lesson", key="deleted-key", content="Deleted")
        deleted.deleted_at = datetime.now(timezone.utc)
        session.add_all([active, deleted])
        await session.flush()

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.aggregated_memory.total == 1
        assert result.aggregated_memory.experience == 1
        assert result.aggregated_memory.lesson == 0

    async def test_tools_always_empty(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """Tools list must always be empty (cannot infer from memory)."""
        emp = await employee_factory()
        await self._add_entries(session, emp.id, ("experience", "test-key", "Test"))

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.manifest_preview.tools == []

    async def test_lesson_content_exactly_200_chars_not_truncated(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """Content exactly 200 chars must not be truncated (no '...')."""
        emp = await employee_factory()
        content_200 = "y" * 200  # exactly 200
        await self._add_entries(
            session,
            emp.id,
            ("lesson", "exact-lesson", content_200),
            ("experience", "exp-1", "filler"),
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        # 200 chars exactly — no "..."
        assert len(result.manifest_preview.prompt) == 200
        assert not result.manifest_preview.prompt.endswith("...")

    async def test_distill_result_fields_populated(
        self, session: AsyncSession, employee_factory
    ) -> None:
        """All DistillResult fields must be populated after a successful distill."""
        emp = await employee_factory()
        await self._add_entries(
            session,
            emp.id,
            ("lesson", "my-command", "A" * 60),
            ("decision", "arch-choice", "B" * 20),
            ("experience", "exp-key", "C" * 10),
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(
            target_skill_slug="my-skill",
            source_preset_slug="mi-shi",
        )
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.new_preset_slug == "mi-shi-skill-my-skill"
        assert isinstance(result.manifest_preview, SkillManifestPreview)
        assert result.manifest_preview.model == "tbd"  # no source preset exists
        assert len(result.manifest_preview.prompt) > 0
        assert "my-command" in result.manifest_preview.commands
        assert "my" in result.manifest_preview.skills
        assert result.aggregated_memory.total == 3
        assert result.source_employee_id == emp.id
        assert result.source_preset_slug == "mi-shi"
