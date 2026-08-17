"""Final Wave F3: Multi-instance + exclusive-FK verification.

Integration tests that actually insert data and verify DB constraints.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base_class import BaseClass
from app.models.entity import Entity
from app.models.instance import Instance
from app.models.user import User
from app.models.workspace import Membership, Workspace


class TestMultiInstance:
    """Verify one entity can have multiple instances across different workspaces."""

    @pytest.mark.asyncio
    async def test_one_entity_two_instances_different_workspaces(
        self, session: AsyncSession, namespace_factory
    ) -> None:
        """Insert 1 Entity + 2 Instances (different workspaces) succeeds."""
        # 1. Create User (for FK chain)
        user = User(username="f3_user", email="f3@test.com", password_hash="hash")
        session.add(user)
        await session.commit()

        # 2. Create BaseClass
        preset = BaseClass(slug="f3-preset", name="F3 Preset")
        session.add(preset)
        await session.commit()

        ns = await namespace_factory()
        # 3. Create Entity
        emp = Entity(namespace_id=ns.id, slug="f3-emp", name="F3 Entity")
        session.add(emp)
        await session.commit()

        # 4. Create 2 Workspaces
        workspace_a = Workspace(namespace_id=ns.id, name="Workspace A", slug="workspace-a")
        workspace_b = Workspace(namespace_id=ns.id, name="Workspace B", slug="workspace-b")
        session.add_all([workspace_a, workspace_b])
        await session.commit()

        # 5. Create 2 Instances (same entity, different workspaces, different workspace_path)
        inst_a = Instance(
            entity_id=emp.id,
            workspace_id=workspace_a.id,
            workspace_path="/workspace/a",
        )
        inst_b = Instance(
            entity_id=emp.id,
            workspace_id=workspace_b.id,
            workspace_path="/workspace/b",
        )
        session.add_all([inst_a, inst_b])
        await session.commit()
        await session.refresh(inst_a)
        await session.refresh(inst_b)

        # 6. Assert both instances created
        assert inst_a.id is not None
        assert inst_a.entity_id == emp.id
        assert inst_a.workspace_id == workspace_a.id
        assert inst_a.workspace_path == "/workspace/a"

        assert inst_b.id is not None
        assert inst_b.entity_id == emp.id
        assert inst_b.workspace_id == workspace_b.id
        assert inst_b.workspace_path == "/workspace/b"


class TestWorkspacePathUniqueness:
    """Verify workspace_path uniqueness among active (non-deleted) instances."""

    @pytest.mark.asyncio
    async def test_duplicate_workspace_path_raises_integrity_error(
        self, session: AsyncSession, namespace_factory
    ) -> None:
        """Inserting two active instances with the same workspace_path fails."""
        ns = await namespace_factory()
        # Create dependent entities
        emp = Entity(namespace_id=ns.id, slug="f3-wp-emp", name="WP Entity")
        workspace_a = Workspace(namespace_id=ns.id, name="WP Workspace A", slug="wp-workspace-a")
        workspace_b = Workspace(namespace_id=ns.id, name="WP Workspace B", slug="wp-workspace-b")
        session.add_all([emp, workspace_a, workspace_b])
        await session.commit()

        # First instance succeeds
        inst_a = Instance(
            entity_id=emp.id,
            workspace_id=workspace_a.id,
            workspace_path="/same/path",
        )
        session.add(inst_a)
        await session.commit()

        # Second instance with same workspace_path fails partial unique index
        inst_b = Instance(
            entity_id=emp.id,
            workspace_id=workspace_b.id,
            workspace_path="/same/path",
        )
        session.add(inst_b)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


class TestMembershipExclusiveFK:
    """Verify Membership CHECK constraint: exactly one of user_id / instance_id non-null."""

    @pytest.mark.asyncio
    async def test_both_null_raises_integrity_error(
        self, session: AsyncSession, namespace_factory
    ) -> None:
        """Membership with both user_id and instance_id NULL fails CHECK constraint."""
        ns = await namespace_factory()
        workspace = Workspace(namespace_id=ns.id, name="Excl Workspace", slug="excl-workspace")
        session.add(workspace)
        await session.commit()

        member = Membership(
            workspace_id=workspace.id,
            user_id=None,
            instance_id=None,
            posx=0,
            posy=0,
        )
        session.add(member)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    @pytest.mark.asyncio
    async def test_user_id_set_instance_id_null_succeeds(
        self, session: AsyncSession, namespace_factory
    ) -> None:
        """Membership with user_id set and instance_id NULL succeeds."""
        user = User(username="f3-mem-user", email="f3mem@test.com", password_hash="hash")
        ns = await namespace_factory()
        workspace = Workspace(namespace_id=ns.id, name="User Workspace", slug="user-workspace")
        session.add_all([user, workspace])
        await session.commit()

        member = Membership(
            workspace_id=workspace.id,
            user_id=user.id,
            instance_id=None,
            posx=0,
            posy=0,
        )
        session.add(member)
        await session.commit()
        await session.refresh(member)

        assert member.id is not None
        assert member.user_id == user.id
        assert member.instance_id is None

    @pytest.mark.asyncio
    async def test_instance_id_set_user_id_null_succeeds(
        self, session: AsyncSession, namespace_factory
    ) -> None:
        """Membership with instance_id set and user_id NULL succeeds."""
        ns = await namespace_factory()
        emp = Entity(namespace_id=ns.id, slug="f3-inst-emp", name="Inst Emp")
        workspace = Workspace(namespace_id=ns.id, name="Inst Workspace", slug="inst-workspace")
        session.add_all([emp, workspace])
        await session.commit()

        inst = Instance(
            entity_id=emp.id,
            workspace_id=workspace.id,
            workspace_path="/workspace/inst-mem",
        )
        session.add(inst)
        await session.commit()

        member = Membership(
            workspace_id=workspace.id,
            user_id=None,
            instance_id=inst.id,
            posx=0,
            posy=0,
        )
        session.add(member)
        await session.commit()
        await session.refresh(member)

        assert member.id is not None
        assert member.user_id is None
        assert member.instance_id == inst.id
