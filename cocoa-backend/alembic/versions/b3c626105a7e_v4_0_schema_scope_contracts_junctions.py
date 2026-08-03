"""v4_0_schema_scope_contracts_junctions

Revision ID: b3c626105a7e
Revises: ad997e162ee8
Create Date: 2026-08-03 09:24:32.639649

v4.0 — Schema, Scope, Gene-only Auth (`.omo/plans/v4-0-schema-auth-scope.md`
+ `.omo/evidence/v4-0-migration-spec.md`).

Single-transaction DDL + data migration (§8.9):

  Phase A — DDL add: scope triples on base_classes / ai_genes /
    capability_market; junction tables (base_class_capabilities,
    entity_capabilities, entity_ai_genes); organization_contracts(+genes);
    namespace_contract_genes; entities.is_cerebellum; user_genes.effect_scope.
  Phase B — data: seed can_* atoms; builtin commands → cmd-* capabilities +
    BaseClass junctions; scope backfill; Membership.role → OrganizationContract
    atoms (+super-admin union, §8.5); old UserGene pack expansion + soft-delete
    (§8.1); entities.capabilities JSONB → entity_capabilities (§6.1/§8.10);
    namespace_contracts role/permissions → namespace_contract_genes (§6.2).
  Phase C — DDL drop: user_genes.permission_keys, memberships.role,
    namespace_contracts.role/permissions, entities.capabilities.
"""

import json
import logging
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

log = logging.getLogger("alembic.runtime.migration")

# revision identifiers, used by Alembic.
revision: str = "b3c626105a7e"
down_revision: Union[str, None] = "ad997e162ee8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Locked seed data (v4.0 plan §Seed 原子; migration-spec §1 taxonomy)
# ---------------------------------------------------------------------------

# (slug, effect_scope) — 16 atoms.
SEED_ATOMS: list[tuple[str, str]] = [
    ("can_manage_organization", "org"),
    ("can_manage_org_members", "org"),
    ("can_manage_namespace", "namespace"),
    ("can_manage_workspace", "workspace"),
    ("can_edit_workspace", "workspace"),
    ("can_view_workspace", "workspace"),
    ("can_operate_workspace", "workspace"),
    ("can_manage_genes", "org"),
    ("can_manage_capabilities", "org"),
    ("can_manage_ai_genes", "org"),
    ("can_clone_base_class", "org"),
    ("can_clone_entity", "namespace"),
    ("can_clone_organization", "org"),
    ("can_clone_workspace", "workspace"),
    ("can_manage_knowledge", "org"),
    ("can_manage_meetings", "workspace"),
]

# Builtin BaseClass slug → command verbs (frozen snapshot of
# app.core.builtin_presets at v4.0; migrations must stay immutable).
PRESET_COMMANDS: dict[str, list[str]] = {
    "mi-shi": ["plan", "decompose", "prioritize"],
    "huan-ling": ["analyze", "clarify", "propose"],
    "an-xing": ["plan", "execute", "build", "test"],
    "an-ying": ["execute", "build", "test"],
    "zhu-jin": ["execute", "build", "test"],
    "ling-shi": ["analyze", "predict", "review"],
    "heng-pan": ["review", "approve", "reject"],
    "you-hun": ["search", "survey", "report"],
    "qian-zhi": ["search", "reference", "survey"],
    "bai-tong": ["look", "analyze", "describe"],
    "jiu-ri": ["delegate", "monitor", "approve"],
    "zong-jian": ["approve", "reject", "delegate"],
}

COMMAND_VERBS: list[str] = sorted({v for verbs in PRESET_COMMANDS.values() for v in verbs})

# §8.3 string role → atoms. Unknown roles (incl. legacy "owner"/"admin")
# fall back to view-only and are logged.
ROLE_ATOMS: dict[str, tuple[str, ...]] = {
    "viewer": ("can_view_workspace",),
    "editor": ("can_view_workspace", "can_edit_workspace"),
    "operator": (
        "can_view_workspace",
        "can_edit_workspace",
        "can_operate_workspace",
    ),
}
_ROLE_RANK = {"viewer": 1, "editor": 2, "operator": 3}


def _role_atoms(role: str | None) -> tuple[str, ...]:
    atoms = ROLE_ATOMS.get(role or "")
    if atoms is None:
        log.info("v4.0 migration: unknown role %r -> can_view_workspace fallback", role)
        return ("can_view_workspace",)
    return atoms


def _new_id() -> str:
    return str(uuid.uuid4())


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # Phase A — DDL (additives only)
    # ------------------------------------------------------------------
    op.create_table(
        "organization_contracts",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("source_pack", sa.String(length=255), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_organization_contracts_org_user",
        "organization_contracts",
        ["organization_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "organization_contract_genes",
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("user_gene_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["organization_contracts.id"]),
        sa.ForeignKeyConstraint(["user_gene_id"], ["user_genes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_organization_contract_genes_gene",
        "organization_contract_genes",
        ["user_gene_id"],
        unique=False,
    )
    op.create_index(
        "uq_organization_contract_genes",
        "organization_contract_genes",
        ["contract_id", "user_gene_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "base_class_capabilities",
        sa.Column("base_class_id", sa.String(length=36), nullable=False),
        sa.Column("capability_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["base_class_id"], ["base_classes.id"]),
        sa.ForeignKeyConstraint(["capability_id"], ["capability_market.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_base_class_capabilities",
        "base_class_capabilities",
        ["base_class_id", "capability_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "entity_ai_genes",
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("ai_gene_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ai_gene_id"], ["ai_genes.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_entity_ai_genes",
        "entity_ai_genes",
        ["entity_id", "ai_gene_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "entity_capabilities",
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("capability_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["capability_id"], ["capability_market.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_entity_capabilities",
        "entity_capabilities",
        ["entity_id", "capability_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "namespace_contract_genes",
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("user_gene_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["namespace_contracts.id"]),
        sa.ForeignKeyConstraint(["user_gene_id"], ["user_genes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_namespace_contract_genes",
        "namespace_contract_genes",
        ["contract_id", "user_gene_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.add_column("ai_genes", sa.Column("scope", sa.String(length=20), server_default="org", nullable=False))
    op.add_column("ai_genes", sa.Column("organization_id", sa.String(length=36), nullable=True))
    op.add_column("ai_genes", sa.Column("namespace_id", sa.String(length=36), nullable=True))
    op.create_index("ix_ai_genes_org", "ai_genes", ["organization_id"], unique=False, postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_foreign_key("fk_ai_genes_namespace", "ai_genes", "namespaces", ["namespace_id"], ["id"])
    op.create_foreign_key("fk_ai_genes_organization", "ai_genes", "organizations", ["organization_id"], ["id"])
    op.create_check_constraint("ck_ai_genes_scope", "ai_genes", "scope IN ('system', 'org', 'namespace')")

    op.add_column("base_classes", sa.Column("scope", sa.String(length=20), server_default="org", nullable=False))
    op.add_column("base_classes", sa.Column("organization_id", sa.String(length=36), nullable=True))
    op.add_column("base_classes", sa.Column("namespace_id", sa.String(length=36), nullable=True))
    op.create_index("ix_base_classes_org", "base_classes", ["organization_id"], unique=False, postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_foreign_key("fk_base_classes_organization", "base_classes", "organizations", ["organization_id"], ["id"])
    op.create_foreign_key("fk_base_classes_namespace", "base_classes", "namespaces", ["namespace_id"], ["id"])
    op.create_check_constraint("ck_base_classes_scope", "base_classes", "scope IN ('system', 'org', 'namespace')")

    op.add_column("capability_market", sa.Column("scope", sa.String(length=20), server_default="org", nullable=False))
    op.add_column("capability_market", sa.Column("organization_id", sa.String(length=36), nullable=True))
    op.add_column("capability_market", sa.Column("namespace_id", sa.String(length=36), nullable=True))
    op.create_index("ix_capability_market_org", "capability_market", ["organization_id"], unique=False, postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_foreign_key("fk_capability_market_organization", "capability_market", "organizations", ["organization_id"], ["id"])
    op.create_foreign_key("fk_capability_market_namespace", "capability_market", "namespaces", ["namespace_id"], ["id"])
    op.create_check_constraint("ck_capability_market_scope", "capability_market", "scope IN ('system', 'org', 'namespace')")

    op.add_column("entities", sa.Column("is_cerebellum", sa.Boolean(), server_default="false", nullable=False))
    op.create_index(
        "uq_entities_cerebellum_per_ns",
        "entities",
        ["namespace_id"],
        unique=True,
        postgresql_where=sa.text("is_cerebellum IS TRUE AND deleted_at IS NULL"),
    )

    # effect_scope starts nullable; backfilled + constrained in Phase C.
    op.add_column("user_genes", sa.Column("effect_scope", sa.String(length=20), nullable=True))
    op.create_check_constraint(
        "ck_user_genes_effect_scope",
        "user_genes",
        "effect_scope IN ('platform', 'org', 'namespace', 'workspace')",
    )

    # ------------------------------------------------------------------
    # Phase B — data migration
    # ------------------------------------------------------------------

    # -- B1. Seed atomic UserGenes (idempotent upsert by slug) --
    atom_ids: dict[str, str] = {}
    for slug, scope in SEED_ATOMS:
        row = conn.execute(
            sa.text("SELECT id FROM user_genes WHERE slug = :s AND deleted_at IS NULL"),
            {"s": slug},
        ).fetchone()
        if row:
            atom_ids[slug] = row[0]
            conn.execute(
                sa.text(
                    "UPDATE user_genes SET effect_scope = :sc, kind = 'builtin',"
                    " name = :s, permission_keys = '[]'::jsonb,"
                    " updated_at = now() WHERE id = :id"
                ),
                {"sc": scope, "s": slug, "id": row[0]},
            )
        else:
            gid = _new_id()
            atom_ids[slug] = gid
            conn.execute(
                sa.text(
                    "INSERT INTO user_genes"
                    " (id, slug, name, kind, effect_scope, permission_keys,"
                    "  description, created_at, updated_at)"
                    " VALUES (:id, :slug, :name, 'builtin', :sc, '[]'::jsonb,"
                    " :desc, now(), now())"
                ),
                {
                    "id": gid,
                    "slug": slug,
                    "name": slug,
                    "sc": scope,
                    "desc": f"Atomic permission: {slug}",
                },
            )

    # -- B2. Builtin command verbs → cmd-* capabilities + BC junctions --
    cmd_cap_ids: dict[str, str] = {}
    for verb in COMMAND_VERBS:
        name = f"cmd-{verb}"
        row = conn.execute(
            sa.text("SELECT id FROM capability_market WHERE name = :n AND deleted_at IS NULL"),
            {"n": name},
        ).fetchone()
        if row:
            cmd_cap_ids[verb] = row[0]
            conn.execute(
                sa.text(
                    "UPDATE capability_market SET type = 'command', scope = 'system',"
                    " organization_id = NULL, namespace_id = NULL,"
                    " tags = ARRAY['builtin', 'command']::varchar[],"
                    " updated_at = now() WHERE id = :id"
                ),
                {"id": row[0]},
            )
        else:
            cid = _new_id()
            cmd_cap_ids[verb] = cid
            conn.execute(
                sa.text(
                    "INSERT INTO capability_market"
                    " (id, name, type, scope, created_via, tags, created_at, updated_at)"
                    " VALUES (:id, :name, 'command', 'system', 'manual',"
                    " ARRAY['builtin', 'command']::varchar[], now(), now())"
                ),
                {"id": cid, "name": name},
            )

    for slug, verbs in PRESET_COMMANDS.items():
        bc = conn.execute(
            sa.text("SELECT id FROM base_classes WHERE slug = :s AND deleted_at IS NULL"),
            {"s": slug},
        ).fetchone()
        if not bc:
            continue
        for verb in verbs:
            exists = conn.execute(
                sa.text(
                    "SELECT 1 FROM base_class_capabilities"
                    " WHERE base_class_id = :bc AND capability_id = :cap"
                    " AND deleted_at IS NULL"
                ),
                {"bc": bc[0], "cap": cmd_cap_ids[verb]},
            ).fetchone()
            if not exists:
                conn.execute(
                    sa.text(
                        "INSERT INTO base_class_capabilities"
                        " (id, base_class_id, capability_id, created_at, updated_at)"
                        " VALUES (:id, :bc, :cap, now(), now())"
                    ),
                    {"id": _new_id(), "bc": bc[0], "cap": cmd_cap_ids[verb]},
                )

    # -- B3. Scope backfill for scoped resources --
    default_org = conn.execute(
        sa.text(
            "SELECT id FROM organizations WHERE slug = 'default' AND deleted_at IS NULL"
            " LIMIT 1"
        )
    ).fetchone()
    if default_org is None:
        default_org = conn.execute(
            sa.text(
                "SELECT id FROM organizations WHERE deleted_at IS NULL"
                " ORDER BY created_at LIMIT 1"
            )
        ).fetchone()
    default_org_id = default_org[0] if default_org else None

    builtin_slugs = tuple(PRESET_COMMANDS.keys())
    conn.execute(
        sa.text(
            "UPDATE base_classes SET scope = 'system', organization_id = NULL,"
            " namespace_id = NULL, updated_at = now()"
            " WHERE slug = ANY(:slugs) AND deleted_at IS NULL"
        ),
        {"slugs": list(builtin_slugs)},
    )
    if default_org_id:
        conn.execute(
            sa.text(
                "UPDATE base_classes SET scope = 'org', organization_id = :org,"
                " updated_at = now()"
                " WHERE NOT (slug = ANY(:slugs)) AND deleted_at IS NULL"
                " AND scope != 'system'"
            ),
            {"org": default_org_id, "slugs": list(builtin_slugs)},
        )
        conn.execute(
            sa.text(
                "UPDATE ai_genes SET scope = 'org', organization_id = :org,"
                " updated_at = now() WHERE deleted_at IS NULL AND scope != 'system'"
            ),
            {"org": default_org_id},
        )
        conn.execute(
            sa.text(
                "UPDATE capability_market SET scope = 'org', organization_id = :org,"
                " updated_at = now()"
                " WHERE deleted_at IS NULL AND scope != 'system'"
            ),
            {"org": default_org_id},
        )

    # -- B4. Membership.role → OrganizationContract atoms (§3 / §8.3–8.5) --
    def ensure_org_contract(org_id: str, user_id: str) -> str:
        row = conn.execute(
            sa.text(
                "SELECT id FROM organization_contracts"
                " WHERE organization_id = :o AND user_id = :u AND deleted_at IS NULL"
            ),
            {"o": org_id, "u": user_id},
        ).fetchone()
        if row:
            return row[0]
        cid = _new_id()
        conn.execute(
            sa.text(
                "INSERT INTO organization_contracts"
                " (id, organization_id, user_id, created_at, updated_at)"
                " VALUES (:id, :o, :u, now(), now())"
            ),
            {"id": cid, "o": org_id, "u": user_id},
        )
        return cid

    def grant_atom(contract_id: str, atom_slug: str, junction: str = "organization_contract_genes") -> None:
        gene_id = atom_ids.get(atom_slug)
        if gene_id is None:
            log.info("v4.0 migration: unknown atom %r dropped", atom_slug)
            return
        exists = conn.execute(
            sa.text(
                f"SELECT 1 FROM {junction}"
                " WHERE contract_id = :c AND user_gene_id = :g AND deleted_at IS NULL"
            ),
            {"c": contract_id, "g": gene_id},
        ).fetchone()
        if not exists:
            conn.execute(
                sa.text(
                    f"INSERT INTO {junction}"
                    " (id, contract_id, user_gene_id, created_at, updated_at)"
                    " VALUES (:id, :c, :g, now(), now())"
                ),
                {"id": _new_id(), "c": contract_id, "g": gene_id},
            )

    membership_rows = conn.execute(
        sa.text(
            "SELECT m.user_id, m.role, n.org_id"
            " FROM memberships m"
            " JOIN workspaces w ON w.id = m.workspace_id AND w.deleted_at IS NULL"
            " JOIN namespaces n ON n.id = w.namespace_id AND n.deleted_at IS NULL"
            " JOIN users u ON u.id = m.user_id AND u.deleted_at IS NULL"
            " WHERE m.deleted_at IS NULL AND m.user_id IS NOT NULL"
        )
    ).fetchall()

    # Highest known role per (org, user); unknown roles -> view fallback (§8.3).
    best: dict[tuple[str, str], tuple[int, str | None]] = {}
    saw_unknown: dict[tuple[str, str], bool] = {}
    for user_id, role, org_id in membership_rows:
        key = (org_id, user_id)
        rank = _ROLE_RANK.get(role or "")
        if rank is None:
            saw_unknown[key] = True
            log.info(
                "v4.0 migration: membership role %r for user %s in org %s"
                " -> can_view_workspace fallback",
                role,
                user_id,
                org_id,
            )
            best.setdefault(key, (0, None))
        else:
            cur = best.get(key, (0, None))
            if rank > cur[0]:
                best[key] = (rank, role)

    for (org_id, user_id), (rank, role) in best.items():
        contract_id = ensure_org_contract(org_id, user_id)
        atoms = _role_atoms(role) if role is not None else ("can_view_workspace",)
        for atom in atoms:
            grant_atom(contract_id, atom)

    # §8.5 — super-admins: upsert contract on default org + full atom union.
    if default_org_id:
        super_admins = conn.execute(
            sa.text(
                "SELECT id FROM users WHERE is_super_admin IS TRUE AND deleted_at IS NULL"
            )
        ).fetchall()
        for (uid,) in super_admins:
            contract_id = ensure_org_contract(default_org_id, uid)
            for slug, _scope in SEED_ATOMS:
                grant_atom(contract_id, slug)

    # §8.1 step 3 — expand old pack permission_keys into existing contracts.
    pack_rows = conn.execute(
        sa.text(
            "SELECT ug.id, ug.slug, ug.permission_keys, uug.user_id"
            " FROM user_genes ug"
            " JOIN user_user_genes uug ON uug.user_gene_id = ug.id"
            "   AND uug.deleted_at IS NULL"
            " JOIN users u ON u.id = uug.user_id AND u.deleted_at IS NULL"
            " WHERE ug.deleted_at IS NULL"
        )
    ).fetchall()
    for gene_id, slug, keys, user_id in pack_rows:
        key_list: list[str] = []
        if isinstance(keys, list):
            key_list = [k for k in keys if isinstance(k, str)]
        elif isinstance(keys, str):
            key_list = [keys]
        matched = [k for k in key_list if k in atom_ids]
        dropped = [k for k in key_list if k not in atom_ids]
        if dropped:
            log.info(
                "v4.0 migration: pack %r keys dropped for user %s: %s",
                slug,
                user_id,
                dropped,
            )
        if not matched:
            continue
        contracts = conn.execute(
            sa.text(
                "SELECT id FROM organization_contracts"
                " WHERE user_id = :u AND deleted_at IS NULL"
            ),
            {"u": user_id},
        ).fetchall()
        for (cid,) in contracts:
            for atom in matched:
                grant_atom(cid, atom)

    # §8.1 step 4 — soft-delete all pack rows (permission_keys non-empty OR
    # slug not can_*) and deprecate the global user_user_genes tenant path.
    conn.execute(
        sa.text(
            "UPDATE user_genes SET deleted_at = now(), updated_at = now()"
            " WHERE deleted_at IS NULL AND ("
            "   (permission_keys IS NOT NULL AND permission_keys != '[]'::jsonb)"
            "   OR slug NOT LIKE 'can\\_%' ESCAPE '\\'"
            " )"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE user_user_genes SET deleted_at = now(), updated_at = now()"
            " WHERE deleted_at IS NULL"
        )
    )

    # -- B5. entities.capabilities JSONB → entity_capabilities (§6.1/§8.10) --
    entity_rows = conn.execute(
        sa.text(
            "SELECT e.id, e.capabilities, n.org_id"
            " FROM entities e"
            " JOIN namespaces n ON n.id = e.namespace_id AND n.deleted_at IS NULL"
            " WHERE e.deleted_at IS NULL"
            " AND e.capabilities IS NOT NULL AND e.capabilities != '[]'::jsonb"
        )
    ).fetchall()

    def _normalize_caps(raw) -> list[dict]:
        if isinstance(raw, list):
            return [c for c in raw if isinstance(c, dict)]
        if isinstance(raw, dict):
            for key in ("items", "capabilities"):
                val = raw.get(key)
                if isinstance(val, list):
                    return [c for c in val if isinstance(c, dict)]
            if raw.get("name"):
                return [raw]
        return []

    def upsert_capability(
        *, name: str, cap_type: str, org_id: str | None, description, config_template
    ) -> str:
        row = conn.execute(
            sa.text("SELECT id FROM capability_market WHERE name = :n AND deleted_at IS NULL"),
            {"n": name},
        ).fetchone()
        if row:
            return row[0]
        cid = _new_id()
        conn.execute(
            sa.text(
                "INSERT INTO capability_market"
                " (id, name, type, scope, organization_id, namespace_id,"
                "  created_via, description, config_template, created_at, updated_at)"
                " VALUES (:id, :n, :t, :sc, :org, NULL, 'manual', :d,"
                " CAST(:ct AS jsonb), now(), now())"
            ),
            {
                "id": cid,
                "n": name,
                "t": cap_type,
                "sc": "org" if org_id else "system",
                "org": org_id,
                "d": description,
                "ct": json.dumps(config_template) if config_template else None,
            },
        )
        return cid

    for entity_id, raw_caps, org_id in entity_rows:
        for item in _normalize_caps(raw_caps):
            name = (item.get("name") or "").strip()
            if not name:
                continue
            cap_type = item.get("type") or "skill"
            if cap_type not in ("skill", "tool", "mcp", "lsp", "command"):
                cap_type = "skill"
            config_template = {
                k: item[k] for k in ("config", "config_template") if k in item
            } or None
            cap_id = upsert_capability(
                name=name,
                cap_type=cap_type,
                org_id=org_id,
                description=item.get("description"),
                config_template=config_template,
            )
            exists = conn.execute(
                sa.text(
                    "SELECT 1 FROM entity_capabilities"
                    " WHERE entity_id = :e AND capability_id = :c AND deleted_at IS NULL"
                ),
                {"e": entity_id, "c": cap_id},
            ).fetchone()
            if not exists:
                conn.execute(
                    sa.text(
                        "INSERT INTO entity_capabilities"
                        " (id, entity_id, capability_id, created_at, updated_at)"
                        " VALUES (:id, :e, :c, now(), now())"
                    ),
                    {"id": _new_id(), "e": entity_id, "c": cap_id},
                )

    # -- B6. namespace_contracts role/permissions → namespace_contract_genes --
    ns_rows = conn.execute(
        sa.text(
            "SELECT nc.id, nc.user_id, nc.role, nc.permissions, n.org_id"
            " FROM namespace_contracts nc"
            " JOIN namespaces n ON n.id = nc.namespace_id AND n.deleted_at IS NULL"
            " JOIN users u ON u.id = nc.user_id AND u.deleted_at IS NULL"
            " WHERE nc.deleted_at IS NULL"
        )
    ).fetchall()

    def _perm_slugs(raw) -> list[str]:
        if isinstance(raw, list):
            return [s for s in raw if isinstance(s, str)]
        if isinstance(raw, dict):
            out: list[str] = []
            for key in ("permission_keys", "permissions", "genes", "slugs", "keys"):
                val = raw.get(key)
                if isinstance(val, list):
                    out.extend(s for s in val if isinstance(s, str))
            return out
        return []

    for contract_id, user_id, role, permissions, org_id in ns_rows:
        # §6.2 — ensure an OrgContract exists (view-only fallback).
        org_contract_id = ensure_org_contract(org_id, user_id)
        grant_atom(org_contract_id, "can_view_workspace")

        atoms = set(_role_atoms(role))
        for slug in _perm_slugs(permissions):
            if slug in atom_ids:
                atoms.add(slug)
            else:
                log.info(
                    "v4.0 migration: ns-contract %s unknown permission key %r dropped",
                    contract_id,
                    slug,
                )
        for atom in sorted(atoms):
            grant_atom(contract_id, atom, junction="namespace_contract_genes")

    # ------------------------------------------------------------------
    # Phase C — DDL drops (after data is safely migrated)
    # ------------------------------------------------------------------
    op.drop_column("entities", "capabilities")
    op.drop_column("memberships", "role")
    op.drop_column("namespace_contracts", "permissions")
    op.drop_column("namespace_contracts", "role")
    op.drop_column("user_genes", "permission_keys")

    # All remaining active user_genes are atoms; default their scope to org
    # before enforcing NOT NULL.
    conn.execute(
        sa.text(
            "UPDATE user_genes SET effect_scope = 'org'"
            " WHERE effect_scope IS NULL"
        )
    )
    op.alter_column("user_genes", "effect_scope", nullable=False)


def downgrade() -> None:
    op.add_column("user_genes", sa.Column("permission_keys", postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True))
    op.alter_column("user_genes", "effect_scope", nullable=True)
    op.drop_constraint("ck_user_genes_effect_scope", "user_genes", type_="check")
    op.drop_column("user_genes", "effect_scope")
    op.add_column("namespace_contracts", sa.Column("role", sa.VARCHAR(length=32), autoincrement=False, nullable=True))
    op.add_column("namespace_contracts", sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True))
    op.add_column("memberships", sa.Column("role", sa.VARCHAR(length=20), autoincrement=False, nullable=True))
    op.add_column("entities", sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True))
    op.drop_index("uq_entities_cerebellum_per_ns", table_name="entities", postgresql_where=sa.text("is_cerebellum IS TRUE AND deleted_at IS NULL"))
    op.drop_column("entities", "is_cerebellum")
    op.drop_constraint("ck_capability_market_scope", "capability_market", type_="check")
    op.drop_constraint("fk_capability_market_namespace", "capability_market", type_="foreignkey")
    op.drop_constraint("fk_capability_market_organization", "capability_market", type_="foreignkey")
    op.drop_index("ix_capability_market_org", table_name="capability_market", postgresql_where=sa.text("deleted_at IS NULL"))
    op.drop_column("capability_market", "namespace_id")
    op.drop_column("capability_market", "organization_id")
    op.drop_column("capability_market", "scope")
    op.drop_constraint("ck_base_classes_scope", "base_classes", type_="check")
    op.drop_constraint("fk_base_classes_namespace", "base_classes", type_="foreignkey")
    op.drop_constraint("fk_base_classes_organization", "base_classes", type_="foreignkey")
    op.drop_index("ix_base_classes_org", table_name="base_classes", postgresql_where=sa.text("deleted_at IS NULL"))
    op.drop_column("base_classes", "namespace_id")
    op.drop_column("base_classes", "organization_id")
    op.drop_column("base_classes", "scope")
    op.drop_constraint("ck_ai_genes_scope", "ai_genes", type_="check")
    op.drop_constraint("fk_ai_genes_organization", "ai_genes", type_="foreignkey")
    op.drop_constraint("fk_ai_genes_namespace", "ai_genes", type_="foreignkey")
    op.drop_index("ix_ai_genes_org", table_name="ai_genes", postgresql_where=sa.text("deleted_at IS NULL"))
    op.drop_column("ai_genes", "namespace_id")
    op.drop_column("ai_genes", "organization_id")
    op.drop_column("ai_genes", "scope")
    op.drop_index("uq_namespace_contract_genes", table_name="namespace_contract_genes", postgresql_where=sa.text("deleted_at IS NULL"))
    op.drop_table("namespace_contract_genes")
    op.drop_index("uq_entity_capabilities", table_name="entity_capabilities", postgresql_where=sa.text("deleted_at IS NULL"))
    op.drop_table("entity_capabilities")
    op.drop_index("uq_entity_ai_genes", table_name="entity_ai_genes", postgresql_where=sa.text("deleted_at IS NULL"))
    op.drop_table("entity_ai_genes")
    op.drop_index("uq_base_class_capabilities", table_name="base_class_capabilities", postgresql_where=sa.text("deleted_at IS NULL"))
    op.drop_table("base_class_capabilities")
    op.drop_index("uq_organization_contract_genes", table_name="organization_contract_genes", postgresql_where=sa.text("deleted_at IS NULL"))
    op.drop_index("ix_organization_contract_genes_gene", table_name="organization_contract_genes")
    op.drop_table("organization_contract_genes")
    op.drop_index("uq_organization_contracts_org_user", table_name="organization_contracts", postgresql_where=sa.text("deleted_at IS NULL"))
    op.drop_table("organization_contracts")
