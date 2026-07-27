"""Tests for Office, Membership, and Corridor models."""

from sqlalchemy import CheckConstraint, Index

from app.models.employee import Employee  # noqa: F401
from app.models.instance import Instance  # noqa: F401
from app.models.office import Corridor, Membership, MembershipRole, Office
from app.models.user import User  # noqa: F401


class TestMembershipRole:
    """MembershipRole enum has exactly three values."""

    def test_three_values(self) -> None:
        members = list(MembershipRole)
        assert len(members) == 3

    def test_contains_owner(self) -> None:
        assert MembershipRole.owner.value == "owner"

    def test_contains_editor(self) -> None:
        assert MembershipRole.editor.value == "editor"

    def test_contains_viewer(self) -> None:
        assert MembershipRole.viewer.value == "viewer"

    def test_is_string_enum(self) -> None:
        assert issubclass(MembershipRole, str)


class TestOfficeModel:
    """Office model has correct table name and columns."""

    def test_table_name(self) -> None:
        assert Office.__tablename__ == "offices"

    def test_inherits_base_model(self) -> None:
        assert hasattr(Office, "id")
        assert hasattr(Office, "created_at")
        assert hasattr(Office, "updated_at")
        assert hasattr(Office, "deleted_at")
        assert hasattr(Office, "soft_delete")

    def test_columns_exist(self) -> None:
        assert hasattr(Office, "name")
        assert hasattr(Office, "slug")
        assert hasattr(Office, "blackboard_ref")

    def test_slug_partial_unique_index(self) -> None:
        """Office slug has a partial unique index WHERE deleted_at IS NULL."""
        table_args = Office.__table_args__
        slug_index = None
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "uq_offices_slug":
                slug_index = arg
                break
        assert slug_index is not None, "uq_offices_slug index not found"
        assert slug_index.unique is True


class TestMembershipModel:
    """Membership model has correct table name, columns, and constraints."""

    def test_table_name(self) -> None:
        assert Membership.__tablename__ == "memberships"

    def test_inherits_base_model(self) -> None:
        assert hasattr(Membership, "id")
        assert hasattr(Membership, "deleted_at")
        assert hasattr(Membership, "soft_delete")

    def test_fk_columns_exist(self) -> None:
        assert hasattr(Membership, "office_id")
        assert hasattr(Membership, "user_id")
        assert hasattr(Membership, "instance_id")

    def test_pos_columns_exist(self) -> None:
        assert hasattr(Membership, "posx")
        assert hasattr(Membership, "posy")

    def test_role_and_permissions_exist(self) -> None:
        assert hasattr(Membership, "role")
        assert hasattr(Membership, "permissions")

    def test_exclusive_fk_check_constraint(self) -> None:
        """Membership has CHECK ((user_id IS NOT NULL) <> (instance_id IS NOT NULL))."""
        table_args = Membership.__table_args__
        ck = None
        for arg in table_args:
            if isinstance(arg, CheckConstraint) and arg.name == "ck_memberships_exclusive_fk":
                ck = arg
                break
        assert ck is not None, (
            "CheckConstraint 'ck_memberships_exclusive_fk' not found"
        )

    def test_office_user_partial_unique_index(self) -> None:
        """Membership has uq_memberships_office_user index."""
        table_args = Membership.__table_args__
        idx = None
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "uq_memberships_office_user":
                idx = arg
                break
        assert idx is not None, (
            "Index 'uq_memberships_office_user' not found"
        )
        assert idx.unique is True

    def test_office_instance_partial_unique_index(self) -> None:
        """Membership has uq_memberships_office_instance index."""
        table_args = Membership.__table_args__
        idx = None
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "uq_memberships_office_instance":
                idx = arg
                break
        assert idx is not None, (
            "Index 'uq_memberships_office_instance' not found"
        )
        assert idx.unique is True

    def test_office_pos_partial_unique_index(self) -> None:
        """Membership has uq_memberships_office_pos index (P9: posx/posy coords)."""
        table_args = Membership.__table_args__
        idx = None
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "uq_memberships_office_pos":
                idx = arg
                break
        assert idx is not None, (
            "Index 'uq_memberships_office_pos' not found"
        )
        assert idx.unique is True

    def test_fk_office(self) -> None:
        """Membership.office_id is FK to offices.id."""
        col = Membership.__table__.c["office_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert str(fk.target_fullname) == "offices.id"

    def test_fk_user(self) -> None:
        """Membership.user_id is FK to users.id, nullable."""
        col = Membership.__table__.c["user_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert str(fk.target_fullname) == "users.id"
        assert col.nullable is True

    def test_fk_instance_string_reference(self) -> None:
        """Membership.instance_id uses forward FK string to instances.id."""
        col = Membership.__table__.c["instance_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert str(fk.target_fullname) == "instances.id"
        assert col.nullable is True


class TestCorridorModel:
    """Corridor model has correct table name, columns, and constraints."""

    def test_table_name(self) -> None:
        assert Corridor.__tablename__ == "corridors"

    def test_inherits_base_model(self) -> None:
        assert hasattr(Corridor, "id")
        assert hasattr(Corridor, "deleted_at")
        assert hasattr(Corridor, "soft_delete")

    def test_columns_exist(self) -> None:
        assert hasattr(Corridor, "office_id")
        assert hasattr(Corridor, "from_membership_id")
        assert hasattr(Corridor, "to_membership_id")
        assert hasattr(Corridor, "is_active")
        assert hasattr(Corridor, "edge_meta")

    def test_is_active_defaults_true(self) -> None:
        col = Corridor.__table__.c["is_active"]
        assert col.default.arg is True
        assert col.nullable is False

    def test_active_edge_partial_unique_index(self) -> None:
        """Corridor has uq_corridors_active_edge partial unique index."""
        table_args = Corridor.__table_args__
        idx = None
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "uq_corridors_active_edge":
                idx = arg
                break
        assert idx is not None, (
            "Index 'uq_corridors_active_edge' not found"
        )
        assert idx.unique is True

    def test_no_acyclicity_constraint(self) -> None:
        """Corridor does NOT enforce acyclicity at DB level (P5 concern)."""
        table_args = Corridor.__table_args__
        for arg in table_args:
            if isinstance(arg, CheckConstraint):
                assert "cycle" not in arg.sqltext.text.lower(), (
                    "Corridor should not have acyclicity check constraint"
                )

    def test_fk_from_membership(self) -> None:
        col = Corridor.__table__.c["from_membership_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert str(fk.target_fullname) == "memberships.id"

    def test_fk_to_membership(self) -> None:
        col = Corridor.__table__.c["to_membership_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert str(fk.target_fullname) == "memberships.id"
