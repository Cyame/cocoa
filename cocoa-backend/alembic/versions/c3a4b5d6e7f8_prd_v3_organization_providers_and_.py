"""prd_v3 organization providers and defaults

Revision ID: c3a4b5d6e7f8
Revises: b1c2d3e4f5a6
Create Date: 2026-07-30 11:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3a4b5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_table("organization_providers"):
        op.create_table(
            "organization_providers",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("organization_id", sa.String(length=36), nullable=False),
            sa.Column("origin", sa.String(length=20), nullable=False),
            sa.Column("catalog_provider_id", sa.String(length=100), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False),
            sa.Column("request_format", sa.String(length=20), nullable=False),
            sa.Column("base_url", sa.Text(), nullable=True),
            sa.Column("api_key_ref", sa.String(length=100), nullable=False),
            sa.Column("default_model", sa.String(length=255), nullable=False),
            sa.Column(
                "models_allowlist",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "verify_ssl",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.Column(
                "models_endpoint_mode",
                sa.String(length=20),
                server_default="inherit",
                nullable=False,
            ),
            sa.Column("models_base_url", sa.Text(), nullable=True),
            sa.Column(
                "enabled",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.Column("last_test_status", sa.String(length=20), nullable=True),
            sa.Column(
                "last_tested_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column(
                "last_test_detail",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.ForeignKeyConstraint(
                ["organization_id"],
                ["organizations.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "uq_organization_providers_org_slug",
            "organization_providers",
            ["organization_id", "slug"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "uq_organization_providers_org_catalog",
            "organization_providers",
            ["organization_id", "catalog_provider_id"],
            unique=True,
            postgresql_where=sa.text(
                "deleted_at IS NULL AND origin = 'catalog'"
            ),
        )

    if not _has_table("base_class_provider_defaults"):
        op.create_table(
            "base_class_provider_defaults",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("base_class_id", sa.String(length=36), nullable=False),
            sa.Column("provider_id", sa.String(length=36), nullable=False),
            sa.Column("model", sa.String(length=255), nullable=False),
            sa.ForeignKeyConstraint(
                ["base_class_id"],
                ["base_classes.id"],
            ),
            sa.ForeignKeyConstraint(
                ["provider_id"],
                ["organization_providers.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "uq_base_class_provider_defaults_base_class",
            "base_class_provider_defaults",
            ["base_class_id"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )

    if not _has_column("organizations", "system_hub_provider_id"):
        op.add_column(
            "organizations",
            sa.Column("system_hub_provider_id", sa.String(length=36), nullable=True),
        )
        op.create_foreign_key(
            "fk_organizations_system_hub_provider",
            "organizations",
            "organization_providers",
            ["system_hub_provider_id"],
            ["id"],
        )
    if not _has_column("organizations", "system_hub_model"):
        op.add_column(
            "organizations",
            sa.Column("system_hub_model", sa.String(length=255), nullable=True),
        )
    if not _has_column("organizations", "cerebellum_default_provider_id"):
        op.add_column(
            "organizations",
            sa.Column(
                "cerebellum_default_provider_id",
                sa.String(length=36),
                nullable=True,
            ),
        )
        op.create_foreign_key(
            "fk_organizations_cerebellum_default_provider",
            "organizations",
            "organization_providers",
            ["cerebellum_default_provider_id"],
            ["id"],
        )
    if not _has_column("organizations", "cerebellum_default_model"):
        op.add_column(
            "organizations",
            sa.Column(
                "cerebellum_default_model", sa.String(length=255), nullable=True
            ),
        )

    if not _has_column("cerebellum_agents", "provider_id"):
        op.add_column(
            "cerebellum_agents",
            sa.Column("provider_id", sa.String(length=36), nullable=True),
        )
        op.create_foreign_key(
            "fk_cerebellum_agents_provider",
            "cerebellum_agents",
            "organization_providers",
            ["provider_id"],
            ["id"],
        )
    if not _has_column("cerebellum_agents", "model"):
        op.add_column(
            "cerebellum_agents",
            sa.Column("model", sa.String(length=255), nullable=True),
        )

    # Mark built-in cerebellum 神职 as internal (API-hidden by default)
    op.execute(
        sa.text(
            """
            UPDATE base_classes
            SET tags = ARRAY['internal', 'system']::varchar[]
            WHERE slug = 'cerebellum-baseclass'
              AND deleted_at IS NULL
            """
        )
    )


def downgrade() -> None:
    if _has_column("cerebellum_agents", "model"):
        op.drop_column("cerebellum_agents", "model")
    if _has_column("cerebellum_agents", "provider_id"):
        op.drop_constraint(
            "fk_cerebellum_agents_provider",
            "cerebellum_agents",
            type_="foreignkey",
        )
        op.drop_column("cerebellum_agents", "provider_id")

    if _has_column("organizations", "cerebellum_default_model"):
        op.drop_column("organizations", "cerebellum_default_model")
    if _has_column("organizations", "cerebellum_default_provider_id"):
        op.drop_constraint(
            "fk_organizations_cerebellum_default_provider",
            "organizations",
            type_="foreignkey",
        )
        op.drop_column("organizations", "cerebellum_default_provider_id")
    if _has_column("organizations", "system_hub_model"):
        op.drop_column("organizations", "system_hub_model")
    if _has_column("organizations", "system_hub_provider_id"):
        op.drop_constraint(
            "fk_organizations_system_hub_provider",
            "organizations",
            type_="foreignkey",
        )
        op.drop_column("organizations", "system_hub_provider_id")

    if _has_table("base_class_provider_defaults"):
        op.drop_index(
            "uq_base_class_provider_defaults_base_class",
            table_name="base_class_provider_defaults",
        )
        op.drop_table("base_class_provider_defaults")

    if _has_table("organization_providers"):
        op.drop_index(
            "uq_organization_providers_org_catalog",
            table_name="organization_providers",
        )
        op.drop_index(
            "uq_organization_providers_org_slug",
            table_name="organization_providers",
        )
        op.drop_table("organization_providers")
