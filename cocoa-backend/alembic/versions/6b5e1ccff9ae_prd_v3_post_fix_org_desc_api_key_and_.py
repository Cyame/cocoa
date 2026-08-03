"""prd_v3_post_fix_org_desc_api_key_and_perm_genes

Revision ID: 6b5e1ccff9ae
Revises: 51e780f715e0
Create Date: 2026-07-30 16:38:09.828391

"""

from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6b5e1ccff9ae"
down_revision: Union[str, None] = "51e780f715e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERMISSION_KEYS = [
    "can_create_workspace",
    "can_delete_workspace",
    "can_edit_central_hub",
    "can_export_audit_log",
    "can_interrupt_instance",
    "can_manage_genes",
    "can_manage_namespaces",
    "can_manage_organization",
    "can_manage_providers",
    "can_manage_users",
    "can_manage_workspaces",
    "can_pause_instance",
    "can_spawn_instance",
    "can_summon_entity",
    "can_view_audit_log",
    "can_view_topology",
    "can_view_workspace",
]


def upgrade() -> None:
    conn = op.get_bind()

    # Idempotent: some local DBs already have these columns from earlier drifts.
    has_desc = conn.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'organizations' AND column_name = 'description'
            """
        )
    ).fetchone()
    if has_desc is None:
        op.add_column(
            "organizations",
            sa.Column("description", sa.Text(), nullable=True),
        )

    key_type = conn.execute(
        sa.text(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'organization_providers' AND column_name = 'api_key_ref'
            """
        )
    ).scalar()
    if key_type == "character varying":
        op.alter_column(
            "organization_providers",
            "api_key_ref",
            existing_type=sa.String(length=100),
            type_=sa.Text(),
            existing_nullable=False,
        )

    # v4.0 note: skip legacy permission-gene seeding when the rebuilt schema
    # no longer carries ``user_genes.permission_keys`` (atoms replace packs).
    _has_permission_keys = "permission_keys" in {
        c["name"] for c in sa.inspect(conn).get_columns("user_genes")
    }
    existing = {
        row[0]
        for row in conn.execute(
            sa.text("SELECT slug FROM user_genes WHERE deleted_at IS NULL")
        ).fetchall()
    }
    for key in _PERMISSION_KEYS if _has_permission_keys else ():
        if key in existing:
            continue
        conn.execute(
            sa.text(
                """
                INSERT INTO user_genes
                    (id, slug, name, kind, permission_keys, description, created_at)
                VALUES
                    (:id, :slug, :name, 'builtin', CAST(:keys AS jsonb), :description, now())
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "slug": key,
                "name": key,
                "keys": json.dumps([key]),
                "description": f"Permission: {key}",
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    for key in _PERMISSION_KEYS:
        conn.execute(
            sa.text(
                """
                UPDATE user_genes
                SET deleted_at = now()
                WHERE slug = :slug AND deleted_at IS NULL
                """
            ),
            {"slug": key},
        )
