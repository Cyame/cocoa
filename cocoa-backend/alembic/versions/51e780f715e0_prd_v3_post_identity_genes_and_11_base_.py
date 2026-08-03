"""prd_v3_post_identity_genes_and_11_base_classes

Revision ID: 51e780f715e0
Revises: c3a4b5d6e7f8
Create Date: 2026-07-30 15:01:56.427407

"""

from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "51e780f715e0"
down_revision: Union[str, None] = "c3a4b5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IDENTITY = {
    "identity-system": (
        "System Admin",
        "Platform super-admin; full world / user / provider control",
        [
            "can_manage_users",
            "can_manage_organization",
            "can_manage_namespaces",
            "can_manage_workspaces",
            "can_manage_providers",
            "can_manage_genes",
            "can_summon_entity",
            "can_spawn_instance",
            "can_interrupt_instance",
            "can_pause_instance",
            "can_edit_central_hub",
            "can_view_workspace",
            "can_view_topology",
            "can_view_audit_log",
            "can_export_audit_log",
            "can_create_workspace",
            "can_delete_workspace",
        ],
    ),
    "identity-org": (
        "World Admin",
        "Organization (world) management",
        [
            "can_manage_organization",
            "can_manage_namespaces",
            "can_manage_workspaces",
            "can_summon_entity",
            "can_spawn_instance",
            "can_view_workspace",
            "can_view_topology",
            "can_create_workspace",
            "can_delete_workspace",
        ],
    ),
    "identity-namespace": (
        "Namespace Admin",
        "Namespace (scenario) management",
        [
            "can_manage_namespaces",
            "can_manage_workspaces",
            "can_summon_entity",
            "can_spawn_instance",
            "can_view_workspace",
            "can_view_topology",
            "can_create_workspace",
        ],
    ),
    "identity-workspace": (
        "Workspace Admin",
        "Workspace operations",
        [
            "can_manage_workspaces",
            "can_summon_entity",
            "can_spawn_instance",
            "can_interrupt_instance",
            "can_pause_instance",
            "can_edit_central_hub",
            "can_view_workspace",
            "can_view_topology",
            "can_create_workspace",
        ],
    ),
    "identity-member": (
        "Member",
        "Baseline visibility and collaboration",
        ["can_view_workspace", "can_view_topology", "can_view_audit_log"],
    ),
}

_LEGACY_MAP = {
    "admin-gene": "identity-system",
    "operator-gene": "identity-workspace",
    "auditor-gene": "identity-namespace",
    "viewer-gene": "identity-member",
}


def upgrade() -> None:
    conn = op.get_bind()

    # v4.0 note: identity packs are dead once ``user_genes.permission_keys``
    # is gone (atoms replace packs; the v4.0 revision seeds the atomic
    # catalog and soft-deletes any pack rows). Skip the whole identity-pack
    # section on fresh rebuilds that already use post-v4.0 metadata.
    _has_permission_keys = "permission_keys" in {
        c["name"] for c in sa.inspect(conn).get_columns("user_genes")
    }

    # --- identity genes upsert ---
    gene_ids: dict[str, str] = {}
    for slug, (name, description, keys) in (
        _IDENTITY.items() if _has_permission_keys else ()
    ):
        row = conn.execute(
            sa.text(
                "SELECT id FROM user_genes WHERE slug = :slug AND deleted_at IS NULL"
            ),
            {"slug": slug},
        ).fetchone()
        if row:
            gene_ids[slug] = row[0]
            conn.execute(
                sa.text(
                    """
                    UPDATE user_genes
                    SET name = :name,
                        description = :description,
                        permission_keys = CAST(:keys AS jsonb),
                        kind = 'builtin',
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {
                    "id": row[0],
                    "name": name,
                    "description": description,
                    "keys": json.dumps(keys),
                },
            )
        else:
            gene_id = str(uuid.uuid4())
            gene_ids[slug] = gene_id
            conn.execute(
                sa.text(
                    """
                    INSERT INTO user_genes
                        (id, slug, name, kind, permission_keys, description, created_at, updated_at)
                    VALUES
                        (:id, :slug, :name, 'builtin', CAST(:keys AS jsonb), :description, now(), now())
                    """
                ),
                {
                    "id": gene_id,
                    "slug": slug,
                    "name": name,
                    "keys": json.dumps(keys),
                    "description": description,
                },
            )

    # --- migrate legacy attachments → identity packs ---
    for legacy_slug, identity_slug in _LEGACY_MAP.items():
        legacy = conn.execute(
            sa.text(
                "SELECT id FROM user_genes WHERE slug = :slug AND deleted_at IS NULL"
            ),
            {"slug": legacy_slug},
        ).fetchone()
        if legacy is None:
            continue
        target_id = gene_ids[identity_slug]
        links = conn.execute(
            sa.text(
                """
                SELECT id, user_id FROM user_user_genes
                WHERE user_gene_id = :gid AND deleted_at IS NULL
                """
            ),
            {"gid": legacy[0]},
        ).fetchall()
        for link_id, user_id in links:
            existing = conn.execute(
                sa.text(
                    """
                    SELECT id FROM user_user_genes
                    WHERE user_id = :uid AND user_gene_id = :gid AND deleted_at IS NULL
                    """
                ),
                {"uid": user_id, "gid": target_id},
            ).fetchone()
            if existing is None:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO user_user_genes
                            (id, user_id, user_gene_id, created_at, updated_at)
                        VALUES (:id, :uid, :gid, now(), now())
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "uid": user_id,
                        "gid": target_id,
                    },
                )
            conn.execute(
                sa.text(
                    """
                    UPDATE user_user_genes
                    SET deleted_at = now(), updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": link_id},
            )
        conn.execute(
            sa.text(
                """
                UPDATE user_genes
                SET deleted_at = now(), updated_at = now()
                WHERE id = :id AND deleted_at IS NULL
                """
            ),
            {"id": legacy[0]},
        )

    if gene_ids:  # skipped entirely on post-v4.0 fresh rebuilds
        # Preserve prior super-admins before rewriting the flag from identity packs.
        prior_super_admins = [
            row[0]
            for row in conn.execute(
                sa.text(
                    """
                    SELECT id FROM users
                    WHERE deleted_at IS NULL AND is_super_admin = true
                    """
                )
            ).fetchall()
        ]

        # --- sync is_super_admin from identity-system ---
        system_id = gene_ids["identity-system"]
        for user_id in prior_super_admins:
            existing = conn.execute(
                sa.text(
                    """
                    SELECT id FROM user_user_genes
                    WHERE user_id = :uid AND user_gene_id = :gid AND deleted_at IS NULL
                    """
                ),
                {"uid": user_id, "gid": system_id},
            ).fetchone()
            if existing is None:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO user_user_genes
                            (id, user_id, user_gene_id, created_at, updated_at)
                        VALUES (:id, :uid, :gid, now(), now())
                        """
                    ),
                    {"id": str(uuid.uuid4()), "uid": user_id, "gid": system_id},
                )
                # Drop lower identity packs when promoting prior super-admins.
                lower_ids = [gene_ids[s] for s in gene_ids if s != "identity-system"]
                if lower_ids:
                    conn.execute(
                        sa.text(
                            """
                            UPDATE user_user_genes
                            SET deleted_at = now(), updated_at = now()
                            WHERE user_id = :uid
                              AND user_gene_id IN :gids
                              AND deleted_at IS NULL
                            """
                        ).bindparams(sa.bindparam("gids", expanding=True)),
                        {"uid": user_id, "gids": lower_ids},
                    )

        conn.execute(
            sa.text(
                """
                UPDATE users
                SET is_super_admin = EXISTS (
                    SELECT 1 FROM user_user_genes uug
                    WHERE uug.user_id = users.id
                      AND uug.user_gene_id = :gid
                      AND uug.deleted_at IS NULL
                ),
                updated_at = now()
                WHERE deleted_at IS NULL
                """
            ),
            {"gid": system_id},
        )

        # Super-admins without identity-system get the pack attached.
        orphans = conn.execute(
            sa.text(
                """
                SELECT id FROM users
                WHERE deleted_at IS NULL
                  AND is_super_admin = true
                  AND NOT EXISTS (
                    SELECT 1 FROM user_user_genes uug
                    WHERE uug.user_id = users.id
                      AND uug.user_gene_id = :gid
                      AND uug.deleted_at IS NULL
                  )
                """
            ),
            {"gid": system_id},
        ).fetchall()
        for (user_id,) in orphans:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO user_user_genes
                        (id, user_id, user_gene_id, created_at, updated_at)
                    VALUES (:id, :uid, :gid, now(), now())
                    """
                ),
                {"id": str(uuid.uuid4()), "uid": user_id, "gid": system_id},
            )

        # Members with no identity gene get identity-member.
        member_id = gene_ids["identity-member"]
        identity_ids = list(gene_ids.values())
        bare_stmt = sa.text(
            """
            SELECT id FROM users
            WHERE deleted_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM user_user_genes uug
                WHERE uug.user_id = users.id
                  AND uug.user_gene_id IN :gids
                  AND uug.deleted_at IS NULL
              )
            """
        ).bindparams(sa.bindparam("gids", expanding=True))
        bare = conn.execute(bare_stmt, {"gids": identity_ids}).fetchall()
        for (user_id,) in bare:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO user_user_genes
                        (id, user_id, user_gene_id, created_at, updated_at)
                    VALUES (:id, :uid, :gid, now(), now())
                    """
                ),
                {"id": str(uuid.uuid4()), "uid": user_id, "gid": member_id},
            )


    # --- upsert 11 public 神职 + internal zong-jian ---
    from app.core.builtin_presets import ALL_BUILTIN_PRESETS

    for preset in ALL_BUILTIN_PRESETS:
        slug = preset["slug"]
        row = conn.execute(
            sa.text(
                "SELECT id FROM base_classes WHERE slug = :slug AND deleted_at IS NULL"
            ),
            {"slug": slug},
        ).fetchone()
        tags = list(preset.get("tags") or [])
        payload = {
            "slug": slug,
            "name": preset["name"],
            "display_name": preset.get("display_name") or preset["name"],
            "description": preset.get("description"),
            "version": preset.get("version") or "1.0.0",
            "manifest": json.dumps(preset.get("manifest") or {}),
            "tags": tags,
        }
        if row:
            conn.execute(
                sa.text(
                    """
                    UPDATE base_classes
                    SET name = :name,
                        display_name = :display_name,
                        description = :description,
                        version = :version,
                        manifest = CAST(:manifest AS jsonb),
                        tags = :tags,
                        updated_at = now()
                    WHERE id = :id
                    """
                ).bindparams(sa.bindparam("tags", type_=sa.ARRAY(sa.String()))),
                {**payload, "id": row[0]},
            )
        else:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO base_classes
                        (id, slug, name, display_name, description, manifest, version, tags,
                         created_at, updated_at)
                    VALUES
                        (:id, :slug, :name, :display_name, :description,
                         CAST(:manifest AS jsonb), :version, :tags,
                         now(), now())
                    """
                ).bindparams(sa.bindparam("tags", type_=sa.ARRAY(sa.String()))),
                {**payload, "id": str(uuid.uuid4())},
            )


def downgrade() -> None:
    raise NotImplementedError("PRD-v3-post identity / 11-base-class seed is not reversible")
