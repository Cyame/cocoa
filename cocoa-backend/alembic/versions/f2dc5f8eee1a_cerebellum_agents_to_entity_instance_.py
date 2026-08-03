"""cerebellum agents to entity instance migration

Migrate live ``cerebellum_agents`` rows to ``Entity(is_cerebellum=True)`` +
``Instance`` (v4-0-migration-spec.md §6.3 + §8.8 tiebreak). Pure data
migration — no schema change. The algorithm lives in
``app/core/cerebellum_migration.py::migrate_cerebellum`` so it is unit-testable
outside Alembic; this revision runs it inside the migration transaction via
``op.get_bind()``.

Revision ID: f2dc5f8eee1a
Revises: 0cdd18da380e
Create Date: 2026-08-04 00:16:14.771270

"""
from typing import Sequence, Union

from alembic import op
from app.core.cerebellum_migration import migrate_cerebellum

# revision identifiers, used by Alembic.
revision: str = 'f2dc5f8eee1a'
down_revision: Union[str, None] = '0cdd18da380e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    migrate_cerebellum(op.get_bind())


def downgrade() -> None:
    """No reverse: legacy rows were soft-deleted; Entity/Instance stay."""
    pass
