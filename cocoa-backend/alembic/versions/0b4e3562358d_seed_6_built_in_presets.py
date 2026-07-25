"""seed 6 built-in presets

Revision ID: 0b4e3562358d
Revises: 2adff570ae77
Create Date: 2026-07-25 17:10:30.974042

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from app.core.builtin_presets import BUILTIN_PRESETS

# revision identifiers, used by Alembic.
revision: str = '0b4e3562358d'
down_revision: Union[str, None] = '2adff570ae77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Insert the 6 built-in presets into ``employee_presets``.

    Each row is wrapped in a subquery check so the migration is idempotent:
    a preset whose slug already exists (e.g. from a manual seed or a previous
    run of this migration) is skipped.
    """
    connection = op.get_bind()

    # Build the table meta for bulk_insert.
    meta = sa.MetaData()
    meta.reflect(only=("employee_presets",), bind=connection)
    employee_presets_table = meta.tables["employee_presets"]

    rows = []
    for preset in BUILTIN_PRESETS:
        slug = preset["slug"]

        # Skip if the slug already exists (idempotency guard).
        existing = connection.execute(
            sa.text("SELECT 1 FROM employee_presets WHERE slug = :s LIMIT 1"),
            {"s": slug},
        ).scalar()
        if existing:
            continue

        import uuid
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        rows.append({
            "id": str(uuid.uuid4()),
            "slug": slug,
            "name": preset["name"],
            "manifest": preset.get("manifest"),
            "version": preset.get("version"),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        })

    if rows:
        op.bulk_insert(employee_presets_table, rows)


def downgrade() -> None:
    """Remove only the 6 built-in presets by slug.

    Presets created by users are **not** affected — the ``WHERE slug IN (...)``
    clause limits deletion to the known built-in slugs.
    """
    slugs = [p["slug"] for p in BUILTIN_PRESETS]
    op.execute(
        sa.text(
            "DELETE FROM employee_presets WHERE slug = ANY(:slugs)"
        ).bindparams(slugs=slugs)
    )
