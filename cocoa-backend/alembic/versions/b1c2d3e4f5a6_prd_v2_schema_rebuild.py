"""PRD-v2 schema rebuild — clean cut (no historical data).

Drops legacy tables created by prior migrations and recreates the PRD-v2
target schema from SQLAlchemy metadata, then seeds default org/namespace
and builtin user_genes + cerebellum-baseclass.
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.db import Base
import app.models  # noqa: F401 — register all tables on Base.metadata

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "0aee66b5fe07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DROP_TABLES = [
    "corridor_nodes",
    "corridors",
    "passages",
    "memberships",
    "namespace_contracts",
    "vault_entries",
    "vaults",
    "fornix_files",
    "blackboard_files",
    "frontal_lobe_kanbans",
    "brainstem_schedules",
    "cerebellum_agents",
    "central_hubs",
    "blackboards",
    "instance_provider_configs",
    "instance_loop_states",
    "deploy_records",
    "memory_entries",
    "memories",
    "instances",
    "capability_market",
    "base_class_ai_genes",
    "ai_genes",
    "base_classes",
    "employee_presets",
    "employees",
    "entities",
    "offices",
    "workspaces",
    "user_user_genes",
    "user_genes",
    "namespaces",
    "organizations",
    "events",
    "users",
]


def upgrade() -> None:
    bind = op.get_bind()
    # Drop in a loop; IF EXISTS so partial prior states still work.
    for table in _DROP_TABLES:
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))

    Base.metadata.create_all(bind=bind)

    # Seed default Organization + Namespace
    org_id = str(uuid.uuid4())
    ns_id = str(uuid.uuid4())
    op.execute(
        sa.text(
            """
            INSERT INTO organizations (id, slug, name, created_at, updated_at)
            VALUES (:id, 'default', 'Default World', now(), now())
            """
        ).bindparams(id=org_id)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO namespaces (id, org_id, slug, name, description, created_at, updated_at)
            VALUES (:id, :org_id, 'default', 'Default Scenario', 'Default scenario namespace', now(), now())
            """
        ).bindparams(id=ns_id, org_id=org_id)
    )

    # Seed builtin user_genes
    genes = [
        (
            "operator-gene",
            "Operator",
            [
                "can_summon_entity",
                "can_spawn_instance",
                "can_interrupt_instance",
                "can_pause_instance",
                "can_edit_central_hub",
                "can_view_workspace",
                "can_view_topology",
                "can_view_audit_log",
            ],
        ),
        (
            "auditor-gene",
            "Auditor",
            [
                "can_view_audit_log",
                "can_export_audit_log",
                "can_view_all_workspaces",
                "can_view_workspace",
                "can_view_topology",
            ],
        ),
        (
            "admin-gene",
            "Admin",
            [
                "can_summon_entity",
                "can_spawn_instance",
                "can_interrupt_instance",
                "can_pause_instance",
                "can_edit_central_hub",
                "can_view_workspace",
                "can_view_topology",
                "can_view_audit_log",
                "can_export_audit_log",
                "can_manage_genes",
                "can_create_workspace",
                "can_delete_workspace",
                "can_manage_organization",
            ],
        ),
        (
            "viewer-gene",
            "Viewer",
            ["can_view_workspace", "can_view_topology", "can_view_audit_log"],
        ),
    ]
    import json

    # v4.0 note: when this rebuild runs with post-v4.0 model metadata,
    # ``user_genes.permission_keys`` no longer exists (atoms replace packs).
    # Skip the legacy pack seeds in that case — the v4.0 revision seeds the
    # atomic catalog instead.
    _has_permission_keys = "permission_keys" in {
        c["name"] for c in sa.inspect(bind).get_columns("user_genes")
    }

    for slug, name, keys in genes if _has_permission_keys else ():
        op.execute(
            sa.text(
                """
                INSERT INTO user_genes (id, slug, name, kind, permission_keys, created_at, updated_at)
                VALUES (:id, :slug, :name, 'builtin', CAST(:keys AS jsonb), now(), now())
                """
            ).bindparams(
                id=str(uuid.uuid4()),
                slug=slug,
                name=name,
                keys=json.dumps(keys),
            )
        )

    # Seed cerebellum-baseclass
    op.execute(
        sa.text(
            """
            INSERT INTO base_classes (id, slug, name, display_name, description, manifest, version, created_at, updated_at)
            VALUES (
                :id, 'cerebellum-baseclass', 'Cerebellum', '小脑',
                'Built-in CentralHub central agent',
                CAST(:manifest AS jsonb), '1.0.0', now(), now()
            )
            """
        ).bindparams(
            id=str(uuid.uuid4()),
            manifest=json.dumps(
                {
                    "system_prompt": "你是世界中枢的小脑：聚合各中枢状态、监控健康、执行定时调度任务。",
                    "commands": [],
                    "tools": [],
                }
            ),
        )
    )

    # Seed PRD 11 神职 + internal zong-jian (display/tags filled; v3-post migration upserts too)
    from app.core.builtin_presets import ALL_BUILTIN_PRESETS

    conn = op.get_bind()
    insert_bc = sa.text(
        """
        INSERT INTO base_classes
            (id, slug, name, display_name, description, manifest, version, tags,
             created_at, updated_at)
        VALUES
            (:id, :slug, :name, :display_name, :description,
             CAST(:manifest AS jsonb), :version, :tags,
             now(), now())
        """
    ).bindparams(sa.bindparam("tags", type_=sa.ARRAY(sa.String())))

    for preset in ALL_BUILTIN_PRESETS:
        conn.execute(
            insert_bc,
            {
                "id": str(uuid.uuid4()),
                "slug": preset["slug"],
                "name": preset["name"],
                "display_name": preset.get("display_name") or preset["name"],
                "description": preset.get("description"),
                "version": preset.get("version") or "1.0.0",
                "manifest": json.dumps(preset.get("manifest") or {}),
                "tags": list(preset.get("tags") or []),
            },
        )


def downgrade() -> None:
    # Irreversible clean-cut migration.
    raise NotImplementedError("PRD-v2 schema rebuild cannot be downgraded")
