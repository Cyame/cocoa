"""add organization provider model overrides

Revision ID: de632dcdc122
Revises: b49542153efc
Create Date: 2026-08-10 16:33:34.044197

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'de632dcdc122'
down_revision: Union[str, None] = 'b49542153efc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Existence guard — this revision must run on BOTH paths:
#   A) a database at b49542153efc (model_overrides does not exist yet), and
#   B) a fresh database where b1c2d3e4f5a6 already rebuilt the full schema
#      from live model metadata (Base.metadata.create_all), which pre-creates
#      organization_providers.model_overrides alongside the base columns.
def _has_column(bind, table: str, column: str) -> bool:
    if table not in set(sa.inspect(bind).get_table_names()):
        return False
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "organization_providers", "model_overrides"):
        return
    op.add_column(
        "organization_providers",
        sa.Column(
            "model_overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "organization_providers", "model_overrides"):
        op.drop_column("organization_providers", "model_overrides")
