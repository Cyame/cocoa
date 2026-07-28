"""update 6 built-in preset prompts: 'TODO P14a' → real system prompts

Revision ID: a8f3b9e21c47
Revises: 5bfdb22e9d96
Create Date: 2026-07-28 17:30:00.000000

P15a prompt fill (2026-07-28): each of the 6 built-in 灵格 now carries a real
per-role system prompt instead of the ``"TODO P14a"`` placeholder shipped by
P14a. This migration updates existing ``employee_presets`` rows so live DBs
match the new ``BUILTIN_PRESETS`` definition.

The UPDATE is keyed on ``slug IN (...)`` and uses ``jsonb_set`` to replace
the ``manifest.prompt`` field only — every other manifest key (model,
commands, provider, skills, tools) is preserved. The migration is safe to
run on fresh DBs (no rows match) and idempotent (running twice is a no-op
because the new prompts are already in place).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from app.core.builtin_presets import BUILTIN_PRESETS

# revision identifiers, used by Alembic.
revision: str = "a8f3b9e21c47"
down_revision: Union[str, None] = "5bfdb22e9d96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace the TODO P14a placeholder prompt on each built-in preset.

    Uses ``jsonb_set`` so all other manifest fields stay untouched. The
    migration only touches the 6 known built-in slugs — user-created
    presets are not modified.
    """
    for preset in BUILTIN_PRESETS:
        slug = preset["slug"]
        new_prompt = preset["manifest"]["prompt"]

        op.execute(
            sa.text(
                """
                UPDATE employee_presets
                SET manifest = jsonb_set(
                    manifest,
                    '{prompt}',
                    to_jsonb(:new_prompt),
                    false
                )
                WHERE slug = :slug
                  AND deleted_at IS NULL
                  AND manifest->>'prompt' = 'TODO P14a'
                """
            ).bindparams(slug=slug, new_prompt=new_prompt)
        )


def downgrade() -> None:
    """Restore the TODO P14a placeholder for downgrade / rollback.

    Mirrors upgrade() exactly in shape so a round-trip brings the DB back
    to the pre-P15a state.
    """
    for preset in BUILTIN_PRESETS:
        slug = preset["slug"]

        op.execute(
            sa.text(
                """
                UPDATE employee_presets
                SET manifest = jsonb_set(
                    manifest,
                    '{prompt}',
                    to_jsonb('TODO P14a'),
                    false
                )
                WHERE slug = :slug
                  AND deleted_at IS NULL
                  AND manifest->>'prompt' != 'TODO P14a'
                """
            ).bindparams(slug=slug)
        )
