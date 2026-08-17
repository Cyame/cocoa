"""Tests for DistillationEngine Protocol and AggregatingDistiller heuristic.

Covers the QA scenarios for the v4.9.3 distill semantics — the engine now
produces **capability candidates** (memory → capability_market) plus a gene
suggestion, not a manifest preview:

- each kebab-case lesson/decision key → one skill candidate (name = key,
  description = truncated content, required_knowledge = key prefix slug)
- key-prefix frequency across non-notepad entries → gene_suggestion
- notepad mirror keys never surface as candidates
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.distillation import (
    AggregatingDistiller,
    CapabilityCandidate,
    DistillationEngine,
    DistillationError,
    DistillResult,
)
from app.models.memory import Memory, MemoryKind
from app.schemas.learning import AggregatedMemoryCount, DistillRequest

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
    """Verify DistillResult dataclass carries capability candidates."""

    def test_fields_present(self) -> None:
        """DistillResult must expose candidates + gene suggestion."""
        candidate = CapabilityCandidate(
            name="debug-memory-leak",
            required_knowledge=["debug"],
        )
        counts = AggregatedMemoryCount()
        dr = DistillResult(
            capability_candidates=[candidate],
            gene_suggestion="debug",
            aggregated_memory=counts,
            source_entity_id="eid",
            source_preset_slug=None,
        )
        assert dr.capability_candidates == [candidate]
        assert dr.gene_suggestion == "debug"
        assert dr.aggregated_memory is counts
        assert dr.source_entity_id == "eid"
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
        entity_id: str,
        *specs: tuple[str, str | None, str | None],
    ) -> None:
        """Insert memory entries. Each spec is (kind, key, content)."""
        for kind, key, content in specs:
            session.add(
                Memory(
                    entity_id=entity_id,
                    kind=kind,
                    key=key,
                    content=content,
                )
            )
        await session.flush()

    # -- Tests ---------------------------------------------------------------

    async def test_empty_memory_raises_distillation_error(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """When entity has no memory entries, distill raises DistillationError."""
        emp = await entity_factory()
        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")

        with pytest.raises(DistillationError) as exc_info:
            await distiller.distill(emp.id, request=request, session=session)
        assert exc_info.value.code == "learning.no_memory"

    async def test_entity_not_found_raises_error(self, session: AsyncSession) -> None:
        """When entity does not exist, distill raises DistillationError."""
        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")

        with pytest.raises(DistillationError) as exc_info:
            await distiller.distill("nonexistent-id", request=request, session=session)
        assert exc_info.value.code == "entity.not_found"

    async def test_mixed_kinds_correct_counts(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """Memory entries of all 4 kinds produce correct aggregated counts."""
        emp = await entity_factory()
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
        assert result.aggregated_memory.notepad == 3
        assert result.aggregated_memory.total == 15

    async def test_kind_filter_respects_filter(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """When kind filter is specified, only those kinds are aggregated."""
        emp = await entity_factory()
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

    async def test_notepad_keys_do_not_pollute_candidates(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """v4.6: notepad mirror keys must not surface as candidates."""
        emp = await entity_factory()
        await self._add_entries(
            session,
            emp.id,
            ("notepad", "notepad/p14a-checkpoint/learnings", "checkpoint note"),
            ("lesson", "debug-concurrency", "Debug concurrency"),
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.aggregated_memory.notepad == 1
        names = {c.name for c in result.capability_candidates}
        assert not any("notepad/p14a" in n for n in names)
        assert "debug-concurrency" in names
        # notepad entries do not feed the gene suggestion either
        assert result.gene_suggestion == "debug"

    async def test_lesson_keys_extract_kebab_case_to_candidates(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """Kebab-case keys from lesson/decision entries become candidates."""
        emp = await entity_factory()
        await self._add_entries(
            session,
            emp.id,
            ("lesson", "debug-concurrency", "Debug concurrency issues"),
            ("decision", "rollback-migration", "Decision to rollback"),
            ("experience", "something-else", "Not a candidate source"),
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        names = {c.name for c in result.capability_candidates}
        assert "debug-concurrency" in names
        assert "rollback-migration" in names
        # experience entries must NOT contribute candidates
        assert "something-else" not in names

    async def test_candidates_max_ten(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """Candidates list must not exceed 10 entries."""
        emp = await entity_factory()
        specs: list[tuple[str, str | None, str | None]] = []
        for i in range(15):
            specs.append(("lesson", f"cmd-{i:02d}", "..."))
        await self._add_entries(session, emp.id, *specs)

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        assert len(result.capability_candidates) <= 10

    async def test_non_kebab_keys_excluded_from_candidates(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """Keys that don't match the kebab-case pattern must not become candidates."""
        emp = await entity_factory()
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

        names = {c.name for c in result.capability_candidates}
        assert "Valid-Key" not in names
        assert "1-starting-digit" not in names

    async def test_longest_lesson_content_truncated_to_200_chars(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """Candidate description (≥ 50 chars) truncated to 200 chars + '...'."""
        emp = await entity_factory()
        long_content = "x" * 210  # 210 chars — triggers truncation
        await self._add_entries(
            session,
            emp.id,
            ("lesson", "long-lesson", long_content),
            ("lesson", "short-lesson", "Short content"),       # shorter, still a candidate
            ("experience", "exp-1", "filler"),                 # ensures non-empty
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        long = next(c for c in result.capability_candidates if c.name == "long-lesson")
        # 200 chars + "..." = 203
        assert len(long.description or "") == 203
        assert (long.description or "").endswith("...")
        assert (long.description or "").startswith("x" * 200)

    async def test_short_lesson_content_passes_through_untouched(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """Short lesson content is used verbatim as the candidate description."""
        emp = await entity_factory()
        await self._add_entries(
            session,
            emp.id,
            ("lesson", "short", "Too short"),
            ("experience", "exp-1", "filler"),
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        short = next(c for c in result.capability_candidates if c.name == "short")
        assert short.description == "Too short"

    async def test_gene_suggestion_from_key_prefix_frequency(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """Most frequent key prefix across entries becomes the gene suggestion."""
        emp = await entity_factory()
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

        assert result.gene_suggestion == "debug"
        # each candidate declares its key prefix as required knowledge
        by_name = {c.name: c for c in result.capability_candidates}
        assert by_name["debug-memory-leak"].required_knowledge == ["debug"]
        assert by_name["deploy-rollback"].required_knowledge == ["deploy"]

    async def test_source_preset_slug_echoed(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """source_preset_slug passes through to the result."""
        emp = await entity_factory()
        await self._add_entries(session, emp.id, ("experience", "test-key", "Test content"))

        distiller = AggregatingDistiller()
        request = DistillRequest(
            target_skill_slug="test-skill", source_preset_slug="mi-shi",
        )
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.source_preset_slug == "mi-shi"
        assert result.source_entity_id == emp.id

    async def test_no_kebab_keys_yields_no_candidates(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """Entries without kebab-case lesson/decision keys → no candidates
        and no gene suggestion (nothing was distilled)."""
        emp = await entity_factory()
        await self._add_entries(
            session, emp.id, ("experience", "test-key", "Test content"),
        )

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.capability_candidates == []
        assert result.gene_suggestion is None

    async def test_soft_deleted_entries_excluded(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """Soft-deleted memory entries must be excluded from aggregation."""
        emp = await entity_factory()
        active = Memory(entity_id=emp.id, kind="experience", key="active-key", content="Active")
        deleted = Memory(entity_id=emp.id, kind="lesson", key="deleted-key", content="Deleted")
        deleted.deleted_at = datetime.now(timezone.utc)
        session.add_all([active, deleted])
        await session.flush()

        distiller = AggregatingDistiller()
        request = DistillRequest(target_skill_slug="test-skill")
        result = await distiller.distill(emp.id, request=request, session=session)

        assert result.aggregated_memory.total == 1
        assert result.aggregated_memory.experience == 1
        assert result.aggregated_memory.lesson == 0

    async def test_lesson_content_exactly_200_chars_not_truncated(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """Content exactly 200 chars must not be truncated (no '...')."""
        emp = await entity_factory()
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

        exact = next(c for c in result.capability_candidates if c.name == "exact-lesson")
        # 200 chars exactly — no "..."
        assert len(exact.description or "") == 200
        assert not (exact.description or "").endswith("...")

    async def test_distill_result_fields_populated(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """All DistillResult fields must be populated after a successful distill."""
        emp = await entity_factory()
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

        assert isinstance(result, DistillResult)
        assert result.capability_candidates
        assert result.gene_suggestion == "my"  # "my" outranks "arch" / "exp"
        assert all(isinstance(c, CapabilityCandidate) for c in result.capability_candidates)
        names = {c.name for c in result.capability_candidates}
        assert "my-command" in names
        assert "arch-choice" in names
        assert result.aggregated_memory.total == 3
        assert result.source_entity_id == emp.id
        assert result.source_preset_slug == "mi-shi"
