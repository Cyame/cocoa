"""Final Wave F3: Multi-instance + exclusive-FK verification.

Integration tests that actually insert data and verify DB constraints.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeePreset, EmployeeRank
from app.models.instance import Instance
from app.models.office import Membership, MembershipRole, Office
from app.models.user import User


class TestMultiInstance:
    """Verify one employee can have multiple instances across different offices."""

    @pytest.mark.asyncio
    async def test_one_employee_two_instances_different_offices(
        self, session: AsyncSession
    ) -> None:
        """Insert 1 Employee + 2 Instances (different offices) succeeds."""
        # 1. Create User (for FK chain)
        user = User(username="f3_user", email="f3@test.com", password_hash="hash")
        session.add(user)
        await session.commit()

        # 2. Create EmployeePreset
        preset = EmployeePreset(slug="f3-preset", name="F3 Preset")
        session.add(preset)
        await session.commit()

        # 3. Create Employee
        emp = Employee(slug="f3-emp", name="F3 Employee", rank=EmployeeRank.researcher)
        session.add(emp)
        await session.commit()

        # 4. Create 2 Offices
        office_a = Office(name="Office A", slug="office-a")
        office_b = Office(name="Office B", slug="office-b")
        session.add_all([office_a, office_b])
        await session.commit()

        # 5. Create 2 Instances (same employee, different offices, different workspace_path)
        inst_a = Instance(
            employee_id=emp.id,
            office_id=office_a.id,
            workspace_path="/workspace/a",
        )
        inst_b = Instance(
            employee_id=emp.id,
            office_id=office_b.id,
            workspace_path="/workspace/b",
        )
        session.add_all([inst_a, inst_b])
        await session.commit()
        await session.refresh(inst_a)
        await session.refresh(inst_b)

        # 6. Assert both instances created
        assert inst_a.id is not None
        assert inst_a.employee_id == emp.id
        assert inst_a.office_id == office_a.id
        assert inst_a.workspace_path == "/workspace/a"

        assert inst_b.id is not None
        assert inst_b.employee_id == emp.id
        assert inst_b.office_id == office_b.id
        assert inst_b.workspace_path == "/workspace/b"


class TestWorkspacePathUniqueness:
    """Verify workspace_path uniqueness among active (non-deleted) instances."""

    @pytest.mark.asyncio
    async def test_duplicate_workspace_path_raises_integrity_error(
        self, session: AsyncSession
    ) -> None:
        """Inserting two active instances with the same workspace_path fails."""
        # Create dependent entities
        emp = Employee(slug="f3-wp-emp", name="WP Employee", rank=EmployeeRank.intern)
        office_a = Office(name="WP Office A", slug="wp-office-a")
        office_b = Office(name="WP Office B", slug="wp-office-b")
        session.add_all([emp, office_a, office_b])
        await session.commit()

        # First instance succeeds
        inst_a = Instance(
            employee_id=emp.id,
            office_id=office_a.id,
            workspace_path="/same/path",
        )
        session.add(inst_a)
        await session.commit()

        # Second instance with same workspace_path fails partial unique index
        inst_b = Instance(
            employee_id=emp.id,
            office_id=office_b.id,
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
        self, session: AsyncSession
    ) -> None:
        """Membership with both user_id and instance_id NULL fails CHECK constraint."""
        office = Office(name="Excl Office", slug="excl-office")
        session.add(office)
        await session.commit()

        member = Membership(
            office_id=office.id,
            user_id=None,
            instance_id=None,
            hex_q=0,
            hex_r=0,
            role=MembershipRole.viewer.value,
        )
        session.add(member)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    @pytest.mark.asyncio
    async def test_user_id_set_instance_id_null_succeeds(
        self, session: AsyncSession
    ) -> None:
        """Membership with user_id set and instance_id NULL succeeds."""
        user = User(username="f3-mem-user", email="f3mem@test.com", password_hash="hash")
        office = Office(name="User Office", slug="user-office")
        session.add_all([user, office])
        await session.commit()

        member = Membership(
            office_id=office.id,
            user_id=user.id,
            instance_id=None,
            hex_q=0,
            hex_r=0,
            role=MembershipRole.viewer.value,
        )
        session.add(member)
        await session.commit()
        await session.refresh(member)

        assert member.id is not None
        assert member.user_id == user.id
        assert member.instance_id is None

    @pytest.mark.asyncio
    async def test_instance_id_set_user_id_null_succeeds(
        self, session: AsyncSession
    ) -> None:
        """Membership with instance_id set and user_id NULL succeeds."""
        emp = Employee(slug="f3-inst-emp", name="Inst Emp", rank=EmployeeRank.intern)
        office = Office(name="Inst Office", slug="inst-office")
        session.add_all([emp, office])
        await session.commit()

        inst = Instance(
            employee_id=emp.id,
            office_id=office.id,
            workspace_path="/workspace/inst-mem",
        )
        session.add(inst)
        await session.commit()

        member = Membership(
            office_id=office.id,
            user_id=None,
            instance_id=inst.id,
            hex_q=0,
            hex_r=0,
            role=MembershipRole.editor.value,
        )
        session.add(member)
        await session.commit()
        await session.refresh(member)

        assert member.id is not None
        assert member.user_id is None
        assert member.instance_id == inst.id
