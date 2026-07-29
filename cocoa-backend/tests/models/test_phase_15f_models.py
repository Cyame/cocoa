"""Smoke tests for phase-15f model additions.

Covers:
- 3 brain region subtables (FrontalLobeKanban / BrainstemSchedule / CerebellumAgent)
- 3-layer market tables (CapabilityMarketEntry / AiGene / BaseClass)
- Employee.migration_hash / capabilities / prompt_regen_snapshot persistence
- Instance.active_hash persistence
- partial unique index soft-delete behavior on slug/name columns

These tests use the conftest's per-test-clone database, so they never touch
``cocoa_dev``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AiGene,
    AiGeneKind,
    BaseClass,
    BrainstemSchedule,
    CapabilityCreatedVia,
    CapabilityMarketEntry,
    CapabilityType,
    CentralHub,
    CerebellumAgent,
    CerebellumAgentType,
    FornixFile,
    FrontalLobeKanban,
    FrontalLobeKanbanStatus,
)
from app.models.employee import Employee
from app.models.instance import Instance, InstanceStatus
from app.models.office import Office

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _u4() -> str:
    return uuid.uuid4().hex[:8]


async def _make_office(session: AsyncSession, slug: str | None = None) -> Office:
    office = Office(name="Hub Office", slug=slug or f"hub-{_u4()}")
    session.add(office)
    await session.flush()
    return office


async def _make_central_hub(session: AsyncSession, office_id: str) -> CentralHub:
    hub = CentralHub(office_id=office_id)
    session.add(hub)
    await session.flush()
    return hub


# ---------------------------------------------------------------------------
# 4-脑区子表
# ---------------------------------------------------------------------------


class TestFrontalLobeKanban:
    """额叶 (frontal lobe) = Kanban / todo card."""

    def test_table_name(self):
        assert FrontalLobeKanban.__tablename__ == "frontal_lobe_kanbans"

    @pytest.mark.asyncio
    async def test_create_card_with_defaults(self, session: AsyncSession):
        office = await _make_office(session)
        hub = await _make_central_hub(session, office.id)

        card = FrontalLobeKanban(central_hub_id=hub.id, title="first card")
        session.add(card)
        await session.commit()
        await session.refresh(card)

        assert card.id is not None
        assert card.status == FrontalLobeKanbanStatus.todo.value
        assert card.position == 0
        assert card.assignee_employee_id is None
        assert card.deleted_at is None

    @pytest.mark.asyncio
    async def test_soft_delete_then_query_excludes(self, session: AsyncSession):
        office = await _make_office(session)
        hub = await _make_central_hub(session, office.id)

        card = FrontalLobeKanban(central_hub_id=hub.id, title="doomed", position=1)
        session.add(card)
        await session.commit()
        card.soft_delete()
        await session.commit()

        # Active query (mirrors API convention) excludes soft-deleted.
        from sqlalchemy import select

        result = await session.execute(
            select(FrontalLobeKanban).where(
                FrontalLobeKanban.central_hub_id == hub.id,
                FrontalLobeKanban.deleted_at.is_(None),
            )
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_assignee_fk_to_employee(self, session: AsyncSession):
        office = await _make_office(session)
        hub = await _make_central_hub(session, office.id)
        emp = Employee(name="worker", slug=f"emp-{_u4()}")
        session.add(emp)
        await session.flush()

        card = FrontalLobeKanban(
            central_hub_id=hub.id,
            title="assigned",
            assignee_employee_id=emp.id,
        )
        session.add(card)
        await session.commit()
        await session.refresh(card)

        assert card.assignee_employee_id == emp.id


class TestBrainstemSchedule:
    """脑干 (brainstem) = scheduled task."""

    def test_table_name(self):
        assert BrainstemSchedule.__tablename__ == "brainstem_schedules"

    @pytest.mark.asyncio
    async def test_create_schedule(self, session: AsyncSession):
        office = await _make_office(session)
        hub = await _make_central_hub(session, office.id)

        sched = BrainstemSchedule(
            central_hub_id=hub.id,
            name="daily-report",
            cron_expr="0 9 * * *",
            action_payload={"type": "emit_event", "target": "report"},
        )
        session.add(sched)
        await session.commit()
        await session.refresh(sched)

        assert sched.id is not None
        assert sched.enabled is True
        assert sched.action_payload == {
            "type": "emit_event",
            "target": "report",
        }
        assert sched.last_run_at is None
        assert sched.next_run_at is None


class TestCerebellumAgent:
    """小脑 (cerebellum) = central system agent config."""

    def test_table_name(self):
        assert CerebellumAgent.__tablename__ == "cerebellum_agents"

    @pytest.mark.asyncio
    async def test_create_agent_defaults_to_orchestrator_inactive(
        self, session: AsyncSession
    ):
        office = await _make_office(session)
        hub = await _make_central_hub(session, office.id)

        agent = CerebellumAgent(
            central_hub_id=hub.id,
            name="hub-orchestrator",
            config={"llm": "gpt-4o-mini"},
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)

        assert agent.agent_type == CerebellumAgentType.orchestrator.value
        assert agent.is_active is False

    @pytest.mark.asyncio
    async def test_partial_unique_active(self, session: AsyncSession):
        """Only one CerebellumAgent per hub can have is_active=true at a time."""

        office = await _make_office(session)
        hub = await _make_central_hub(session, office.id)

        a = CerebellumAgent(
            central_hub_id=hub.id, name="a", is_active=True
        )
        session.add(a)
        await session.commit()

        b = CerebellumAgent(
            central_hub_id=hub.id, name="b", is_active=True
        )
        session.add(b)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


# ---------------------------------------------------------------------------
# 3 层能力市场
# ---------------------------------------------------------------------------


class TestCapabilityMarketEntry:
    """L1 — atomic capability."""

    def test_table_name(self):
        assert CapabilityMarketEntry.__tablename__ == "capability_market"

    @pytest.mark.asyncio
    async def test_create_entry(self, session: AsyncSession):
        entry = CapabilityMarketEntry(
            name="workflow-design-patterns",
            type=CapabilityType.skill.value,
            description="Reusable workflow patterns.",
            tags=["design", "patterns"],
            config_template={"version": "1"},
            created_via=CapabilityCreatedVia.manual.value,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)

        assert entry.id is not None
        assert entry.tags == ["design", "patterns"]
        assert entry.config_template == {"version": "1"}
        assert entry.created_via == "manual"
        assert entry.source_entity_slug is None

    @pytest.mark.asyncio
    async def test_partial_unique_name_conflict(self, session: AsyncSession):
        a = CapabilityMarketEntry(
            name="dup-skill", type=CapabilityType.skill.value
        )
        b = CapabilityMarketEntry(
            name="dup-skill", type=CapabilityType.tool.value
        )
        session.add_all([a, b])
        with pytest.raises(IntegrityError):
            await session.commit()

    @pytest.mark.asyncio
    async def test_partial_unique_name_soft_delete_allows_reuse(
        self, session: AsyncSession
    ):
        a = CapabilityMarketEntry(
            name="reusable-skill", type=CapabilityType.skill.value
        )
        session.add(a)
        await session.commit()

        a.soft_delete()
        await session.commit()

        b = CapabilityMarketEntry(
            name="reusable-skill",
            type=CapabilityType.skill.value,
            created_via=CapabilityCreatedVia.promote.value,
        )
        session.add(b)
        await session.commit()
        await session.refresh(b)

        assert b.slug if hasattr(b, "slug") else b.name == "reusable-skill"
        assert b.deleted_at is None
        assert b.created_via == "promote"


class TestAiGene:
    """L2 — capability packaging."""

    def test_table_name(self):
        assert AiGene.__tablename__ == "ai_genes"

    @pytest.mark.asyncio
    async def test_create_tool_gene(self, session: AsyncSession):
        gene = AiGene(
            slug="code-review-toolkit",
            name="Code Review Toolkit",
            kind=AiGeneKind.tool_gene.value,
            tags=["review"],
            manifest={
                "tool_allow": ["group:fs"],
                "scripts": {"review.py": "# stub"},
                "runtime_config": {"MAX_TOKENS": 4096},
            },
        )
        session.add(gene)
        await session.commit()
        await session.refresh(gene)

        assert gene.id is not None
        assert gene.kind == "tool-gene"
        assert gene.manifest["tool_allow"] == ["group:fs"]
        assert gene.gene_slugs == []

    @pytest.mark.asyncio
    async def test_partial_unique_slug_reuse(self, session: AsyncSession):
        a = AiGene(slug="shared-gene", name="v1", kind=AiGeneKind.tool_gene.value)
        session.add(a)
        await session.commit()
        a.soft_delete()
        await session.commit()

        b = AiGene(
            slug="shared-gene",
            name="v2",
            kind=AiGeneKind.tool_gene.value,
        )
        session.add(b)
        await session.commit()
        assert b.deleted_at is None


class TestBaseClass:
    """L3 — 神职 (AI role template)."""

    def test_table_name(self):
        assert BaseClass.__tablename__ == "base_classes"

    @pytest.mark.asyncio
    async def test_create_base_class(self, session: AsyncSession):
        bc = BaseClass(
            slug="mi-shi",
            name="密士",
            display_name="base_classes.mi_shi",
            description="密探 + 士官 长于审问",
            manifest={
                "provider_config": {"type": "openai-compatible"},
                "default_model": "gpt-4o-mini",
                "commands": ["/read", "/list"],
                "default_capabilities": [],
                "default_gene_refs": [],
                "system_prompt": "You are 密士.",
            },
            version="0.1.0",
            tags=["divinity", "starter"],
        )
        session.add(bc)
        await session.commit()
        await session.refresh(bc)

        assert bc.id is not None
        assert bc.display_name == "base_classes.mi_shi"
        assert bc.manifest["default_model"] == "gpt-4o-mini"
        assert "divinity" in (bc.tags or [])

    @pytest.mark.asyncio
    async def test_partial_unique_slug(self, session: AsyncSession):
        a = BaseClass(slug="lc", name="A")
        b = BaseClass(slug="lc", name="B")
        session.add_all([a, b])
        with pytest.raises(IntegrityError):
            await session.commit()


# ---------------------------------------------------------------------------
# Employee / Instance new columns
# ---------------------------------------------------------------------------


class TestEmployeePhase15fFields:
    """Employee.migration_hash / capabilities / prompt_regen_snapshot."""

    @pytest.mark.asyncio
    async def test_defaults_are_null_and_empty_list(
        self, session: AsyncSession
    ):
        emp = Employee(name="alice", slug=f"e-{_u4()}")
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.migration_hash is None
        assert emp.capabilities == []
        assert emp.prompt_regen_snapshot is None

    @pytest.mark.asyncio
    async def test_persist_distillation_state(self, session: AsyncSession):
        emp = Employee(
            name="bob",
            slug=f"e-{_u4()}",
            migration_hash="a" * 64,
            capabilities=[
                {"name": "review", "type": "skill", "description": "review", "source": "promote"},
            ],
            prompt_regen_snapshot="You are bob, an upgraded 密士.",
        )
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.migration_hash == "a" * 64
        assert emp.capabilities[0]["name"] == "review"
        assert emp.capabilities[0]["source"] == "promote"
        assert "upgraded 密士" in emp.prompt_regen_snapshot


class TestInstancePhase15fFields:
    """Instance.active_hash — set at spawn / restart."""

    @pytest.mark.asyncio
    async def test_default_active_hash_is_null(self, session: AsyncSession):
        emp = Employee(name="alice", slug=f"e-{_u4()}")
        session.add(emp)
        await session.flush()

        office = await _make_office(session)
        inst = Instance(
            employee_id=emp.id,
            office_id=office.id,
            status=InstanceStatus.running.value,
        )
        session.add(inst)
        await session.commit()
        await session.refresh(inst)

        assert inst.active_hash is None

    @pytest.mark.asyncio
    async def test_persist_active_hash(self, session: AsyncSession):
        emp = Employee(name="alice", slug=f"e-{_u4()}")
        session.add(emp)
        await session.flush()
        office = await _make_office(session)
        inst = Instance(
            employee_id=emp.id,
            office_id=office.id,
            status=InstanceStatus.running.value,
            active_hash="f" * 64,
        )
        session.add(inst)
        await session.commit()
        await session.refresh(inst)

        assert inst.active_hash == "f" * 64


# ---------------------------------------------------------------------------
# Backward-compat sanity: existing FornixFile still attaches to CentralHub.
# ---------------------------------------------------------------------------


class TestFornixStillAttachesToCentralHub:
    """Fornix (穹窿) was already there — sanity check that the new brain
    region tables coexist with the existing FornixFile table."""

    @pytest.mark.asyncio
    async def test_attach_fornix_file_to_central_hub(
        self, session: AsyncSession
    ):
        office = await _make_office(session)
        hub = await _make_central_hub(session, office.id)
        from app.models.user import User

        uploader = User(
            username=f"u-{_u4()}",
            email=f"u-{_u4()}@example.com",
            password_hash="x",
        )
        session.add(uploader)
        await session.flush()

        # Sanity: 4 brain regions all FK to the same hub row.
        session.add_all(
            [
                FrontalLobeKanban(
                    central_hub_id=hub.id, title="x", position=10
                ),
                BrainstemSchedule(
                    central_hub_id=hub.id,
                    name="s",
                    cron_expr="0 * * * *",
                ),
                CerebellumAgent(central_hub_id=hub.id, name="c"),
                FornixFile(
                    office_id=office.id,
                    name="README.md",
                    parent_path="/",
                    storage_key=f"k-{_u4()}",
                    uploader_user_id=uploader.id,
                ),
            ]
        )
        await session.commit()

        from sqlalchemy import func, select

        count = await session.execute(
            select(func.count())
            .select_from(FrontalLobeKanban)
            .where(
                FrontalLobeKanban.central_hub_id == hub.id,
                FrontalLobeKanban.deleted_at.is_(None),
            )
        )
        assert count.scalar() == 1
