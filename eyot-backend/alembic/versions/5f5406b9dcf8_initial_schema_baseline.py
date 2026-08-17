"""initial schema baseline

Revision ID: 5f5406b9dcf8
Revises:
Create Date: 2026-08-17 10:04:09.263296

Baseline created during the Cocoa → Eyot rename: the 35 incremental Alembic
revisions were squashed into a single build-from-models migration. Uses
``Base.metadata.create_all`` so SQLAlchemy topologically orders tables by
foreign-key dependency (autogenerate's naive ordering was not reliable).
"""
from typing import Sequence, Union

from alembic import op
import app.models  # noqa: F401  (register every table on Base.metadata)
import sqlalchemy as sa  # noqa: F401
from app.core.db import Base


# revision identifiers, used by Alembic.
revision: str = '5f5406b9dcf8'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)