"""Tests for Instance model and InstanceStatus enum."""

from app.models.instance import Instance, InstanceStatus


class TestInstanceStatus:
    """Verify the InstanceStatus enum."""

    def test_has_seven_values(self) -> None:
        """InstanceStatus must contain exactly 7 states."""
        members = list(InstanceStatus)
        assert len(members) == 7

    def test_expected_values_present(self) -> None:
        """All required lifecycle states must be present."""
        expected = {
            "creating",
            "pending",
            "deploying",
            "running",
            "restarting",
            "failed",
            "deleting",
        }
        actual = {m.value for m in InstanceStatus}
        assert actual == expected

    def test_is_string_enum(self) -> None:
        """Values must be strings (not PG native enum)."""
        for member in InstanceStatus:
            assert isinstance(member.value, str)

    def test_default_status_is_creating(self) -> None:
        """The default status for new instances is 'creating'."""
        assert InstanceStatus.creating.value == "creating"


class TestInstanceModel:
    """Verify Instance SQLAlchemy model structure."""

    def test_tablename(self) -> None:
        """Table name must be 'instances'."""
        assert Instance.__tablename__ == "instances"

    def test_imports(self) -> None:
        """Model must be importable and a class."""
        assert isinstance(Instance, type)

    def test_entity_id_column_exists(self) -> None:
        """entity_id FK column must be present."""
        col = Instance.__table__.columns["entity_id"]
        assert col is not None
        assert not col.nullable

    def test_workspace_id_column_exists(self) -> None:
        """workspace_id FK column must be present (forward reference to Workspace model)."""
        col = Instance.__table__.columns["workspace_id"]
        assert col is not None
        assert not col.nullable

    def test_workspace_path_column_is_nullable(self) -> None:
        """workspace_path must allow NULL."""
        col = Instance.__table__.columns["workspace_path"]
        assert col.nullable is True

    def test_status_column_default(self) -> None:
        """status column default is 'creating'."""
        col = Instance.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == "creating"

    def test_runtime_config_is_json(self) -> None:
        """runtime_config column must exist and be nullable."""
        col = Instance.__table__.columns["runtime_config"]
        assert col is not None
        assert col.nullable is True

    def test_proxy_token_column(self) -> None:
        """proxy_token column must exist and be nullable."""
        col = Instance.__table__.columns["proxy_token"]
        assert col is not None
        assert col.nullable is True

    def test_inherits_base_model(self) -> None:
        """Instance must have id, created_at, updated_at, deleted_at from BaseModel."""
        assert "id" in Instance.__table__.columns
        assert "created_at" in Instance.__table__.columns
        assert "updated_at" in Instance.__table__.columns
        assert "deleted_at" in Instance.__table__.columns

    def test_entity_id_foreign_key(self) -> None:
        """entity_id must have a ForeignKey to entities.id."""
        col = Instance.__table__.columns["entity_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        # Use _colspec to avoid FK resolution which requires the entities
        # table to be present in metadata (created in Todo 2, not yet loaded).
        assert fks[0]._colspec == "entities.id"

    def test_workspace_id_foreign_key(self) -> None:
        """workspace_id must have a ForeignKey to workspaces.id (forward reference)."""
        col = Instance.__table__.columns["workspace_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        # Use _colspec to avoid FK resolution which requires the workspaces
        # table to be present in metadata (forward reference, created in Todo 4).
        assert fks[0]._colspec == "workspaces.id"

    def test_workspace_path_partial_unique_index(self) -> None:
        """workspace_path must have a partial unique index for active instances."""
        indexes = {idx.name: idx for idx in Instance.__table__.indexes}
        assert "uq_instances_workspace_path" in indexes

    def test_entity_workspace_unique_constraint(self) -> None:
        """(entity_id, workspace_id) has a partial unique index.
        PRD v3.4 made one-instance-per-(entity, workspace) the contract
        (``uq_instances_workspace_entity``); the index must be partial on
        ``deleted_at IS NULL`` so soft-deleted rows do not block recreation.
        """
        indexes = {idx.name: idx for idx in Instance.__table__.indexes}
        idx = indexes.get("uq_instances_workspace_entity")
        assert idx is not None
        cols = {c.name for c in idx.columns}
        assert cols == {"entity_id", "workspace_id"}
        assert idx.unique is True
        assert "deleted_at" in str(idx.dialect_options["postgresql"].get("where", ""))
