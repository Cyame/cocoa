"""v4.9.3 knowledge dual-dimension columns

Revision ID: 05072e4afb42
Revises: ddb7bd415907
Create Date: 2026-08-06 10:49:42.237263

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '05072e4afb42'
down_revision: Union[str, None] = 'ddb7bd415907'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded: the PRD-v2 rebuild baseline (b1c2d3e4f5a6) runs
    # ``Base.metadata.create_all`` against live model metadata, so fresh
    # builds already carry these columns before this revision runs;
    # incremental DBs (cocoa_dev) need the explicit add.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "required_knowledge" not in {
        c["name"] for c in insp.get_columns("capability_market")
    }:
        op.add_column(
            "capability_market",
            sa.Column(
                "required_knowledge",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )
    if "has_knowledge" not in {c["name"] for c in insp.get_columns("base_classes")}:
        op.add_column(
            "base_classes",
            sa.Column(
                "has_knowledge",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )
    if "has_knowledge" not in {c["name"] for c in insp.get_columns("entities")}:
        op.add_column(
            "entities",
            sa.Column(
                "has_knowledge",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )


def downgrade() -> None:
    op.drop_column("entities", "has_knowledge")
    op.drop_column("base_classes", "has_knowledge")
    op.drop_column("capability_market", "required_knowledge")
