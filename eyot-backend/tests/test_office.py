"""Tests for Workspace, Membership, and Passage models."""

from sqlalchemy import CheckConstraint, Index

from app.models.entity import Entity  # noqa: F401
from app.models.instance import Instance  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.workspace import Membership, Passage, Workspace


class TestWorkspaceModel:
    """Workspace model has correct table name and columns."""

    def test_table_name(self) -> None:
        assert Workspace.__tablename__ == "workspaces"

    def test_inherits_base_model(self) -> None:
        assert hasattr(Workspace, "id")
        assert hasattr(Workspace, "created_at")
        assert hasattr(Workspace, "updated_at")
        assert hasattr(Workspace, "deleted_at")
        assert hasattr(Workspace, "soft_delete")

    def test_columns_exist(self) -> None:
        assert hasattr(Workspace, "name")
        assert hasattr(Workspace, "slug")
        assert hasattr(Workspace, "namespace_id")

    def test_slug_partial_unique_index(self) -> None:
        """Workspace slug has a partial unique index WHERE deleted_at IS NULL."""
        table_args = Workspace.__table_args__
        slug_index = None
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "uq_workspaces_namespace_slug":
                slug_index = arg
                break
        assert slug_index is not None, "uq_workspaces_namespace_slug index not found"
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
        assert hasattr(Membership, "workspace_id")
        assert hasattr(Membership, "user_id")
        assert hasattr(Membership, "instance_id")

    def test_pos_columns_exist(self) -> None:
        assert hasattr(Membership, "posx")
        assert hasattr(Membership, "posy")

    def test_role_dropped_and_permissions_exist(self) -> None:
        # v4.0: the static role column was physically dropped (design §4.2).
        assert not hasattr(Membership, "role")
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

    def test_workspace_user_partial_unique_index(self) -> None:
        """Membership has uq_memberships_workspace_user index."""
        table_args = Membership.__table_args__
        idx = None
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "uq_memberships_workspace_user":
                idx = arg
                break
        assert idx is not None, (
            "Index 'uq_memberships_workspace_user' not found"
        )
        assert idx.unique is True

    def test_workspace_instance_partial_unique_index(self) -> None:
        """Membership has uq_memberships_workspace_instance index."""
        table_args = Membership.__table_args__
        idx = None
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "uq_memberships_workspace_instance":
                idx = arg
                break
        assert idx is not None, (
            "Index 'uq_memberships_workspace_instance' not found"
        )
        assert idx.unique is True

    def test_workspace_pos_partial_unique_index(self) -> None:
        """Membership has uq_memberships_workspace_pos index (P9: posx/posy coords)."""
        table_args = Membership.__table_args__
        idx = None
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "uq_memberships_workspace_pos":
                idx = arg
                break
        assert idx is not None, (
            "Index 'uq_memberships_workspace_pos' not found"
        )
        assert idx.unique is True

    def test_fk_workspace(self) -> None:
        """Membership.workspace_id is FK to workspaces.id."""
        col = Membership.__table__.c["workspace_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert str(fk.target_fullname) == "workspaces.id"

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


class TestPassageModel:
    """Passage model has correct table name, columns, and constraints."""

    def test_table_name(self) -> None:
        assert Passage.__tablename__ == "passages"

    def test_inherits_base_model(self) -> None:
        assert hasattr(Passage, "id")
        assert hasattr(Passage, "deleted_at")
        assert hasattr(Passage, "soft_delete")

    def test_columns_exist(self) -> None:
        assert hasattr(Passage, "workspace_id")
        assert hasattr(Passage, "from_membership_id")
        assert hasattr(Passage, "to_membership_id")
        assert hasattr(Passage, "is_active")
        assert hasattr(Passage, "edge_meta")

    def test_is_active_defaults_true(self) -> None:
        col = Passage.__table__.c["is_active"]
        assert col.default.arg is True
        assert col.nullable is False

    def test_active_edge_partial_unique_index(self) -> None:
        """Passage has uq_passages_active_edge partial unique index."""
        table_args = Passage.__table_args__
        idx = None
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "uq_passages_active_edge":
                idx = arg
                break
        assert idx is not None, (
            "Index 'uq_passages_active_edge' not found"
        )
        assert idx.unique is True

    def test_no_acyclicity_constraint(self) -> None:
        """Passage does NOT enforce acyclicity at DB level (P5 concern)."""
        table_args = Passage.__table_args__
        for arg in table_args:
            if isinstance(arg, CheckConstraint):
                assert "cycle" not in arg.sqltext.text.lower(), (
                    "Passage should not have acyclicity check constraint"
                )

    def test_fk_from_membership(self) -> None:
        col = Passage.__table__.c["from_membership_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert str(fk.target_fullname) == "memberships.id"

    def test_fk_to_membership(self) -> None:
        col = Passage.__table__.c["to_membership_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert str(fk.target_fullname) == "memberships.id"
