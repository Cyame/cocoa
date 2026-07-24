"""Tests for Employee and EmployeePreset models."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.employee import Employee, EmployeePreset, EmployeeRank


class TestEmployeeRank:
    """Tests for the EmployeeRank enum."""

    def test_rank_has_three_values(self):
        members = list(EmployeeRank)
        assert len(members) == 3
        values = {m.value for m in members}
        assert values == {"intern", "researcher", "director"}

    def test_rank_is_string_enum(self):
        assert isinstance(EmployeeRank.intern.value, str)
        assert EmployeeRank.intern.value == "intern"


class TestEmployeePresetTable:
    """Tests for the EmployeePreset model table."""

    def test_table_name(self):
        assert EmployeePreset.__tablename__ == "employee_presets"

    @pytest.mark.asyncio
    async def test_create_preset(self, session: AsyncSession):
        preset = EmployeePreset(slug="helper", name="Helper", version="1.0")
        session.add(preset)
        await session.commit()
        await session.refresh(preset)

        assert preset.id is not None
        assert preset.slug == "helper"
        assert preset.name == "Helper"
        assert preset.version == "1.0"
        assert preset.manifest is None
        assert preset.deleted_at is None

    @pytest.mark.asyncio
    async def test_create_preset_with_manifest(self, session: AsyncSession):
        manifest_data = {"system_prompt": "You are helpful.", "tools": ["search"]}
        preset = EmployeePreset(
            slug="worker", name="Worker", manifest=manifest_data
        )
        session.add(preset)
        await session.commit()
        await session.refresh(preset)

        assert preset.manifest == manifest_data

    @pytest.mark.asyncio
    async def test_partial_unique_active_conflict(self, session: AsyncSession):
        a = EmployeePreset(slug="dup", name="First")
        b = EmployeePreset(slug="dup", name="Second")
        session.add_all([a, b])
        with pytest.raises(IntegrityError):
            await session.commit()

    @pytest.mark.asyncio
    async def test_partial_unique_soft_deleted_allows_reuse(self, session: AsyncSession):
        a = EmployeePreset(slug="reuse", name="First")
        session.add(a)
        await session.commit()

        a.soft_delete()
        await session.commit()

        b = EmployeePreset(slug="reuse", name="Second")
        session.add(b)
        await session.commit()
        await session.refresh(b)

        assert b.slug == "reuse"
        assert b.deleted_at is None


class TestEmployeeTable:
    """Tests for the Employee model table."""

    def test_table_name(self):
        assert Employee.__tablename__ == "employees"

    @pytest.mark.asyncio
    async def test_create_employee(self, session: AsyncSession):
        emp = Employee(slug="alice", name="Alice", rank=EmployeeRank.researcher)
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.id is not None
        assert emp.slug == "alice"
        assert emp.name == "Alice"
        assert emp.rank == "researcher"
        assert emp.preset_slug is None
        assert emp.display_name is None
        assert emp.display_color is None
        assert emp.deleted_at is None

    @pytest.mark.asyncio
    async def test_default_rank_is_intern(self, session: AsyncSession):
        emp = Employee(slug="bob", name="Bob")
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.rank == EmployeeRank.intern

    @pytest.mark.asyncio
    async def test_create_employee_with_display_fields(self, session: AsyncSession):
        emp = Employee(
            slug="charlie",
            name="Charlie",
            rank=EmployeeRank.director,
            display_name="Charlie the Director",
            display_color="#FF5733",
        )
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.display_name == "Charlie the Director"
        assert emp.display_color == "#FF5733"

    @pytest.mark.asyncio
    async def test_partial_unique_active_conflict(self, session: AsyncSession):
        a = Employee(slug="dupe", name="First")
        b = Employee(slug="dupe", name="Second")
        session.add_all([a, b])
        with pytest.raises(IntegrityError):
            await session.commit()

    @pytest.mark.asyncio
    async def test_partial_unique_soft_deleted_allows_reuse(self, session: AsyncSession):
        a = Employee(slug="reuse", name="First")
        session.add(a)
        await session.commit()

        a.soft_delete()
        await session.commit()

        b = Employee(slug="reuse", name="Second")
        session.add(b)
        await session.commit()
        await session.refresh(b)

        assert b.slug == "reuse"
        assert b.deleted_at is None


class TestEmployeePresetReference:
    """Tests for the logical reference from Employee.preset_slug to EmployeePreset.slug.

    No DB-level FK constraint exists because EmployeePreset.slug uses a
    partial unique index (soft-delete), which PostgreSQL does not accept as
    a foreign-key target.
    """

    @pytest.mark.asyncio
    async def test_preset_slug_references_valid_preset(self, session: AsyncSession):
        preset = EmployeePreset(slug="engineer", name="Engineer")
        session.add(preset)
        await session.commit()

        emp = Employee(
            slug="eve", name="Eve", preset_slug="engineer", rank=EmployeeRank.researcher
        )
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.preset_slug == "engineer"

    @pytest.mark.asyncio
    async def test_preset_slug_null_allowed(self, session: AsyncSession):
        emp = Employee(slug="grace", name="Grace", rank=EmployeeRank.intern)
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.preset_slug is None

    @pytest.mark.asyncio
    async def test_preset_slug_survives_preset_update(self, session: AsyncSession):
        preset = EmployeePreset(slug="temp", name="Temporary")
        session.add(preset)
        await session.commit()

        emp = Employee(
            slug="hank", name="Hank", preset_slug="temp", rank=EmployeeRank.intern
        )
        session.add(emp)
        await session.commit()

        preset.name = "Permanent"
        await session.commit()
        await session.refresh(emp)

        assert emp.preset_slug == "temp"

    @pytest.mark.asyncio
    async def test_employee_preset_slug_stored_as_plain_string(self, session: AsyncSession):
        """preset_slug has no DB FK constraint, so any string value is accepted."""
        emp = Employee(
            slug="iris", name="Iris", preset_slug="no-such-preset", rank=EmployeeRank.intern
        )
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.preset_slug == "no-such-preset"
