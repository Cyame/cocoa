"""v4.6 notepad memory writeback

Data migration: legacy ``instance_loop_states.notepad_refs`` file-path
structure → ``Memory(kind=notepad)`` rows + memory-id refs (v4-6 plan 存量
迁移). ``MemoryKind.notepad`` is a Python-enum extension only — the
``memories.kind`` column is an unconstrained VARCHAR(20), so no schema
change is required.

Revision ID: 2645619c35ad
Revises: 1d65b2c05cd1
Create Date: 2026-08-04 22:27:46.702170

"""
from typing import Sequence, Union

from alembic import op
from app.core.notepad_migration import migrate_notepad_refs

# revision identifiers, used by Alembic.
revision: str = '2645619c35ad'
down_revision: Union[str, None] = '1d65b2c05cd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    migrate_notepad_refs(op.get_bind())


def downgrade() -> None:
    """No reverse: rewritten refs are already memory ids; Memory rows stay."""
