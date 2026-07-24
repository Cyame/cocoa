"""Tests for Blackboard, BlackboardFile, Vault, VaultEntry models and VaultEntrySourceType enum."""

from sqlalchemy import CheckConstraint

from app.models.blackboard import (
    Blackboard,
    BlackboardFile,
    Vault,
    VaultEntry,
    VaultEntrySourceType,
)


class TestVaultEntrySourceType:
    """Verify the VaultEntrySourceType enum."""

    def test_has_two_values(self) -> None:
        """VaultEntrySourceType must contain exactly 2 values."""
        members = list(VaultEntrySourceType)
        assert len(members) == 2

    def test_expected_values_present(self) -> None:
        """Both archival source types must be present."""
        expected = {"blackboard_file", "workspace_file"}
        actual = {m.value for m in VaultEntrySourceType}
        assert actual == expected

    def test_is_string_enum(self) -> None:
        """Values must be strings (not PG native enum)."""
        for member in VaultEntrySourceType:
            assert isinstance(member.value, str)


class TestBlackboardModel:
    """Verify Blackboard SQLAlchemy model structure."""

    def test_tablename(self) -> None:
        """Table name must be 'blackboards'."""
        assert Blackboard.__tablename__ == "blackboards"

    def test_imports(self) -> None:
        """Model must be importable and a class."""
        assert isinstance(Blackboard, type)

    def test_office_id_column_exists(self) -> None:
        """office_id FK column must be present and NOT NULL."""
        col = Blackboard.__table__.columns["office_id"]
        assert col is not None
        assert not col.nullable

    def test_content_column_nullable(self) -> None:
        """content must allow NULL."""
        col = Blackboard.__table__.columns["content"]
        assert col.nullable is True

    def test_manual_notes_column_nullable(self) -> None:
        """manual_notes must allow NULL."""
        col = Blackboard.__table__.columns["manual_notes"]
        assert col.nullable is True

    def test_inherits_base_model(self) -> None:
        """Blackboard must have id, created_at, updated_at, deleted_at."""
        assert "id" in Blackboard.__table__.columns
        assert "created_at" in Blackboard.__table__.columns
        assert "updated_at" in Blackboard.__table__.columns
        assert "deleted_at" in Blackboard.__table__.columns

    def test_office_id_foreign_key(self) -> None:
        """office_id must have a ForeignKey to offices.id."""
        col = Blackboard.__table__.columns["office_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert fk._colspec == "offices.id"

    def test_office_id_partial_unique_index(self) -> None:
        """office_id must have a partial unique index for 1:1 enforcement."""
        indexes = {idx.name: idx for idx in Blackboard.__table__.indexes}
        assert "uq_blackboards_office" in indexes


class TestBlackboardFileModel:
    """Verify BlackboardFile SQLAlchemy model structure."""

    def test_tablename(self) -> None:
        """Table name must be 'blackboard_files'."""
        assert BlackboardFile.__tablename__ == "blackboard_files"

    def test_imports(self) -> None:
        """Model must be importable and a class."""
        assert isinstance(BlackboardFile, type)

    def test_office_id_column_exists(self) -> None:
        """office_id FK column must be present and NOT NULL."""
        col = BlackboardFile.__table__.columns["office_id"]
        assert col is not None
        assert not col.nullable

    def test_name_column_not_null(self) -> None:
        """name must be NOT NULL."""
        col = BlackboardFile.__table__.columns["name"]
        assert not col.nullable

    def test_parent_path_column_nullable(self) -> None:
        """parent_path must allow NULL."""
        col = BlackboardFile.__table__.columns["parent_path"]
        assert col.nullable is True

    def test_storage_key_column_not_null(self) -> None:
        """storage_key must be NOT NULL."""
        col = BlackboardFile.__table__.columns["storage_key"]
        assert not col.nullable

    def test_content_type_column_nullable(self) -> None:
        """content_type must allow NULL."""
        col = BlackboardFile.__table__.columns["content_type"]
        assert col.nullable is True

    def test_file_size_column_nullable(self) -> None:
        """file_size must allow NULL."""
        col = BlackboardFile.__table__.columns["file_size"]
        assert col.nullable is True

    def test_is_directory_default(self) -> None:
        """is_directory default is False."""
        col = BlackboardFile.__table__.columns["is_directory"]
        assert col.default is not None
        assert col.default.arg is False

    def test_uploader_user_id_nullable(self) -> None:
        """uploader_user_id must allow NULL."""
        col = BlackboardFile.__table__.columns["uploader_user_id"]
        assert col.nullable is True

    def test_uploader_instance_id_nullable(self) -> None:
        """uploader_instance_id must allow NULL."""
        col = BlackboardFile.__table__.columns["uploader_instance_id"]
        assert col.nullable is True

    def test_inherits_base_model(self) -> None:
        """BlackboardFile must have id, created_at, updated_at, deleted_at."""
        assert "id" in BlackboardFile.__table__.columns
        assert "created_at" in BlackboardFile.__table__.columns
        assert "updated_at" in BlackboardFile.__table__.columns
        assert "deleted_at" in BlackboardFile.__table__.columns

    def test_office_id_foreign_key(self) -> None:
        """office_id must have a ForeignKey to offices.id."""
        col = BlackboardFile.__table__.columns["office_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert fk._colspec == "offices.id"

    def test_uploader_user_id_foreign_key(self) -> None:
        """uploader_user_id must have a ForeignKey to users.id."""
        col = BlackboardFile.__table__.columns["uploader_user_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert fk._colspec == "users.id"

    def test_uploader_instance_id_foreign_key(self) -> None:
        """uploader_instance_id must have a ForeignKey to instances.id."""
        col = BlackboardFile.__table__.columns["uploader_instance_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert fk._colspec == "instances.id"

    def test_path_partial_unique_index(self) -> None:
        """(office_id, parent_path, name) partial unique index must exist."""
        indexes = {idx.name: idx for idx in BlackboardFile.__table__.indexes}
        assert "uq_blackboard_files_path" in indexes

    def test_storage_key_global_unique_index(self) -> None:
        """storage_key must have a global (non-partial) unique index."""
        indexes = {idx.name: idx for idx in BlackboardFile.__table__.indexes}
        assert "uq_blackboard_files_storage_key" in indexes
        # Global unique = no postgresql_where clause
        idx = indexes["uq_blackboard_files_storage_key"]
        assert idx.dialect_options.get("postgresql_where") is None

    def test_exclusive_uploader_check_constraint(self) -> None:
        """Must have CHECK: exactly one of uploader_user_id or uploader_instance_id is NOT NULL."""
        constraints = {
            c.name: c
            for c in BlackboardFile.__table__.constraints
            if isinstance(c, CheckConstraint)
        }
        assert "ck_blackboard_files_exclusive_uploader" in constraints


class TestVaultModel:
    """Verify Vault SQLAlchemy model structure."""

    def test_tablename(self) -> None:
        """Table name must be 'vaults'."""
        assert Vault.__tablename__ == "vaults"

    def test_imports(self) -> None:
        """Model must be importable and a class."""
        assert isinstance(Vault, type)

    def test_office_id_column_exists(self) -> None:
        """office_id FK column must be present and NOT NULL."""
        col = Vault.__table__.columns["office_id"]
        assert col is not None
        assert not col.nullable

    def test_inherits_base_model(self) -> None:
        """Vault must have id, created_at, updated_at, deleted_at."""
        assert "id" in Vault.__table__.columns
        assert "created_at" in Vault.__table__.columns
        assert "updated_at" in Vault.__table__.columns
        assert "deleted_at" in Vault.__table__.columns

    def test_office_id_foreign_key(self) -> None:
        """office_id must have a ForeignKey to offices.id."""
        col = Vault.__table__.columns["office_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert fk._colspec == "offices.id"

    def test_office_id_partial_unique_index(self) -> None:
        """office_id must have a partial unique index for 1:1 enforcement."""
        indexes = {idx.name: idx for idx in Vault.__table__.indexes}
        assert "uq_vaults_office" in indexes


class TestVaultEntryModel:
    """Verify VaultEntry SQLAlchemy model structure."""

    def test_tablename(self) -> None:
        """Table name must be 'vault_entries'."""
        assert VaultEntry.__tablename__ == "vault_entries"

    def test_imports(self) -> None:
        """Model must be importable and a class."""
        assert isinstance(VaultEntry, type)

    def test_vault_id_column_exists(self) -> None:
        """vault_id FK column must be present and NOT NULL."""
        col = VaultEntry.__table__.columns["vault_id"]
        assert col is not None
        assert not col.nullable

    def test_source_type_column_not_null(self) -> None:
        """source_type must be NOT NULL."""
        col = VaultEntry.__table__.columns["source_type"]
        assert not col.nullable

    def test_source_type_max_length(self) -> None:
        """source_type must be String(20)."""
        col = VaultEntry.__table__.columns["source_type"]
        assert col.type.length == 20

    def test_source_ref_column_nullable(self) -> None:
        """source_ref must allow NULL."""
        col = VaultEntry.__table__.columns["source_ref"]
        assert col.nullable is True

    def test_archived_key_column_nullable(self) -> None:
        """archived_key must allow NULL."""
        col = VaultEntry.__table__.columns["archived_key"]
        assert col.nullable is True

    def test_archived_at_column_nullable(self) -> None:
        """archived_at must allow NULL."""
        col = VaultEntry.__table__.columns["archived_at"]
        assert col.nullable is True

    def test_inherits_base_model(self) -> None:
        """VaultEntry must have id, created_at, updated_at, deleted_at."""
        assert "id" in VaultEntry.__table__.columns
        assert "created_at" in VaultEntry.__table__.columns
        assert "updated_at" in VaultEntry.__table__.columns
        assert "deleted_at" in VaultEntry.__table__.columns

    def test_no_updated_at_override(self) -> None:
        """VaultEntry must NOT override updated_at (inherits BaseModel)."""
        col = VaultEntry.__table__.columns["updated_at"]
        # BaseModel.updated_at has server_default=func.now(), onupdate=func.now()
        # No extra logic — just verify the column exists (it's inherited).
        assert col is not None
        # The column is inherited from BaseModel, so it has server_default.
        assert col.server_default is not None

    def test_vault_id_foreign_key(self) -> None:
        """vault_id must have a ForeignKey to vaults.id."""
        col = VaultEntry.__table__.columns["vault_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert fk._colspec == "vaults.id"

    def test_no_explicit_table_args(self) -> None:
        """VaultEntry must NOT have __table_args__ (inherits without extra constraints)."""
        assert getattr(VaultEntry, "__table_args__", None) is None
