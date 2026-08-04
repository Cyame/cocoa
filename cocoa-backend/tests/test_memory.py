"""Tests for Memory append-log model and MemoryKind enum."""

from app.models.memory import Memory, MemoryKind


class TestMemoryKind:
    """Verify the MemoryKind enum."""

    def test_has_five_values(self) -> None:
        """MemoryKind must contain exactly 5 kinds (v4.6 adds notepad)."""
        members = list(MemoryKind)
        assert len(members) == 5

    def test_expected_values_present(self) -> None:
        """All required memory kinds must be present."""
        expected = {"experience", "lesson", "decision", "problem", "notepad"}
        actual = {m.value for m in MemoryKind}
        assert actual == expected

    def test_is_string_enum(self) -> None:
        """Values must be strings (stored as String(20) in PG)."""
        for member in MemoryKind:
            assert isinstance(member.value, str)


class TestMemoryModel:
    """Verify Memory SQLAlchemy model structure."""

    def test_imports(self) -> None:
        """Model must be importable and a class."""
        assert isinstance(Memory, type)

    def test_tablename(self) -> None:
        """Table name must be 'memories'."""
        assert Memory.__tablename__ == "memories"

    def test_no_updated_at_column(self) -> None:
        """Memory must NOT have an updated_at column (append-only log)."""
        assert "updated_at" not in Memory.__table__.columns

    def test_has_no_updated_at_on_instance(self) -> None:
        """Memory.updated_at is None (column overridden from BaseModel)."""
        entry = Memory()
        assert entry.updated_at is None

    def test_inherits_base_model_id(self) -> None:
        """Must have id, created_at, deleted_at from BaseModel."""
        assert "id" in Memory.__table__.columns
        assert "created_at" in Memory.__table__.columns
        assert "deleted_at" in Memory.__table__.columns

    def test_entity_id_column(self) -> None:
        """entity_id must be present and NOT NULL."""
        col = Memory.__table__.columns["entity_id"]
        assert col is not None
        assert not col.nullable

    def test_entity_id_foreign_key(self) -> None:
        """entity_id must have a ForeignKey to entities.id."""
        col = Memory.__table__.columns["entity_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        # Use _colspec to avoid FK resolution which requires the entities
        # table to be present in metadata (created in Todo 2, not yet loaded).
        assert fks[0]._colspec == "entities.id"

    def test_kind_column(self) -> None:
        """kind must be String(20) and NOT NULL."""
        col = Memory.__table__.columns["kind"]
        assert col is not None
        assert not col.nullable
        assert hasattr(col.type, "length")
        assert col.type.length == 20

    def test_key_column(self) -> None:
        """key must be nullable VARCHAR(255)."""
        col = Memory.__table__.columns["key"]
        assert col is not None
        assert col.nullable is True
        assert hasattr(col.type, "length")
        assert col.type.length == 255

    def test_content_column(self) -> None:
        """content must be nullable TEXT."""
        col = Memory.__table__.columns["content"]
        assert col is not None
        assert col.nullable is True

    def test_source_instance_id_column(self) -> None:
        """source_instance_id must be nullable VARCHAR(36) with NO foreign key."""
        col = Memory.__table__.columns["source_instance_id"]
        assert col is not None
        assert col.nullable is True
        fks = list(col.foreign_keys)
        assert len(fks) == 0, "source_instance_id must NOT have a foreign key"

    def test_entity_created_index_exists(self) -> None:
        """An index on (entity_id, created_at) must exist."""
        indexes = {idx.name: idx for idx in Memory.__table__.indexes}
        assert "ix_memories_entity_created" in indexes

    def test_entity_created_index_not_unique(self) -> None:
        """The (entity_id, created_at) index must NOT be unique."""
        indexes = {idx.name: idx for idx in Memory.__table__.indexes}
        idx = indexes["ix_memories_entity_created"]
        assert idx.unique is False

    def test_no_partial_unique_index(self) -> None:
        """Memory must have NO partial unique index (append-log allows duplicates)."""
        for idx in Memory.__table__.indexes:
            assert idx.unique is False, (
                f"Unexpected unique index: {idx.name} (append-log must allow duplicates)"
            )
