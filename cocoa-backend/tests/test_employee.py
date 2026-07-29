"""Tests for Entity and BaseClass models."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity, EntityRank
from app.models.base_class import BaseClass


class TestEntityRank:
    """Tests for the EntityRank enum."""

    def test_rank_has_two_values(self):
        members = list(EntityRank)
        assert len(members) == 2
        values = {m.value for m in members}
        assert values == {"intern", "researcher"}

    def test_rank_is_string_enum(self):
        assert isinstance(EntityRank.intern.value, str)
        assert EntityRank.intern.value == "intern"


class TestBaseClassTable:
    """Tests for the BaseClass model table."""

    def test_table_name(self):
        assert BaseClass.__tablename__ == "base_classes"

    @pytest.mark.asyncio
    async def test_create_preset(self, session: AsyncSession):
        preset = BaseClass(slug="helper", name="Helper", version="1.0")
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
        preset = BaseClass(
            slug="worker", name="Worker", manifest=manifest_data
        )
        session.add(preset)
        await session.commit()
        await session.refresh(preset)

        assert preset.manifest == manifest_data

    @pytest.mark.asyncio
    async def test_partial_unique_active_conflict(self, session: AsyncSession):
        a = BaseClass(slug="dup", name="First")
        b = BaseClass(slug="dup", name="Second")
        session.add_all([a, b])
        with pytest.raises(IntegrityError):
            await session.commit()

    @pytest.mark.asyncio
    async def test_partial_unique_soft_deleted_allows_reuse(self, session: AsyncSession):
        a = BaseClass(slug="reuse", name="First")
        session.add(a)
        await session.commit()

        a.soft_delete()
        await session.commit()

        b = BaseClass(slug="reuse", name="Second")
        session.add(b)
        await session.commit()
        await session.refresh(b)

        assert b.slug == "reuse"
        assert b.deleted_at is None


class TestEntityTable:
    """Tests for the Entity model table."""

    def test_table_name(self):
        assert Entity.__tablename__ == "entities"

    @pytest.mark.asyncio
    async def test_create_entity(self, session: AsyncSession, namespace_factory):
        ns = await namespace_factory()
        emp = Entity(
            namespace_id=ns.id,
            slug="alice",
            name="Alice",
            rank=EntityRank.researcher,
        )
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
    async def test_default_rank_is_intern(self, session: AsyncSession, namespace_factory):
        ns = await namespace_factory()
        emp = Entity(namespace_id=ns.id, slug="bob", name="Bob")
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.rank == EntityRank.intern.value

    @pytest.mark.asyncio
    async def test_create_entity_with_display_fields(
        self, session: AsyncSession, namespace_factory
    ):
        ns = await namespace_factory()
        emp = Entity(
            namespace_id=ns.id,
            slug="charlie",
            name="Charlie",
            rank=EntityRank.researcher,
            display_name="Charlie the Researcher",
            display_color="#FF5733",
        )
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.display_name == "Charlie the Researcher"
        assert emp.display_color == "#FF5733"

    @pytest.mark.asyncio
    async def test_partial_unique_active_conflict(
        self, session: AsyncSession, namespace_factory
    ):
        ns = await namespace_factory()
        a = Entity(namespace_id=ns.id, slug="dupe", name="First")
        b = Entity(namespace_id=ns.id, slug="dupe", name="Second")
        session.add_all([a, b])
        with pytest.raises(IntegrityError):
            await session.commit()

    @pytest.mark.asyncio
    async def test_partial_unique_soft_deleted_allows_reuse(
        self, session: AsyncSession, namespace_factory
    ):
        ns = await namespace_factory()
        a = Entity(namespace_id=ns.id, slug="reuse", name="First")
        session.add(a)
        await session.commit()

        a.soft_delete()
        await session.commit()

        b = Entity(namespace_id=ns.id, slug="reuse", name="Second")
        session.add(b)
        await session.commit()
        await session.refresh(b)

        assert b.slug == "reuse"
        assert b.deleted_at is None


class TestBaseClassReference:
    """Logical reference from Entity.preset_slug to BaseClass.slug."""

    @pytest.mark.asyncio
    async def test_preset_slug_references_valid_preset(
        self, session: AsyncSession, namespace_factory
    ):
        ns = await namespace_factory()
        preset = BaseClass(slug="engineer", name="Engineer")
        session.add(preset)
        await session.commit()

        emp = Entity(
            namespace_id=ns.id,
            slug="eve",
            name="Eve",
            preset_slug="engineer",
            rank=EntityRank.researcher,
        )
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.preset_slug == "engineer"

    @pytest.mark.asyncio
    async def test_preset_slug_null_allowed(
        self, session: AsyncSession, namespace_factory
    ):
        ns = await namespace_factory()
        emp = Entity(
            namespace_id=ns.id, slug="grace", name="Grace", rank=EntityRank.intern
        )
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.preset_slug is None

    @pytest.mark.asyncio
    async def test_preset_slug_survives_preset_update(
        self, session: AsyncSession, namespace_factory
    ):
        ns = await namespace_factory()
        preset = BaseClass(slug="temp", name="Temporary")
        session.add(preset)
        await session.commit()

        emp = Entity(
            namespace_id=ns.id,
            slug="hank",
            name="Hank",
            preset_slug="temp",
            rank=EntityRank.intern,
        )
        session.add(emp)
        await session.commit()

        preset.name = "Permanent"
        await session.commit()
        await session.refresh(emp)

        assert emp.preset_slug == "temp"

    @pytest.mark.asyncio
    async def test_base_class_slug_stored_as_plain_string(
        self, session: AsyncSession, namespace_factory
    ):
        """preset_slug has no DB FK constraint, so any string value is accepted."""
        ns = await namespace_factory()
        emp = Entity(
            namespace_id=ns.id,
            slug="iris",
            name="Iris",
            preset_slug="no-such-preset",
            rank=EntityRank.intern,
        )
        session.add(emp)
        await session.commit()
        await session.refresh(emp)

        assert emp.preset_slug == "no-such-preset"
