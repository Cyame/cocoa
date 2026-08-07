"""Learning API routes (P10 Wave 2 + phase-15f capability lifecycle + v4.9.3).

Endpoints for the skill-distillation and capability-lifecycle flows.
v4.9.3 炼化 chain — three-role division:

- **reap** = Instance memory → capability draft (instance-private)
  ``POST /learning/instances/{iid}/reap``
- **distill** = Entity memory → org-level **capability_market** entries
  (``created_via="distill"``, required_knowledge declared, no has)
  ``POST /learning/entities/{eid}/distill``
- **promote** = Instance → Entity (回魂/派生), aggregates has_knowledge
  ``POST /learning/entities/{eid}/promote``
- **transmute** = Entity → BaseClass (神职), genes + has_knowledge mount
  ``POST /learning/entities/{eid}/transmute``

Other endpoints:
- GET  /learning/memories/{entity_id}/summary  — aggregated memory counts
- GET  /learning/presets/{preset_id}           — historical distill result (B4 compat)
- POST /learning/capabilities/combine          — N capabilities → 1 gene
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.capabilities import upsert_capability
from app.core.distillation import (
    AggregatingDistiller,
    CapabilityCandidate,
    DistillationError,
    DistillResult,
    LLMDistiller,
    aggregate_memory_counts,
)
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.event_types import (
    LEARNING_COMPOSED,
    LEARNING_DISTILLATION_COMPLETED,
    LEARNING_PROMOTED,
    LEARNING_REAPED,
    LEARNING_TRANSMUTED,
)
from app.core.events import emit
from app.core.migration_hash import (
    compute_entity_migration_hash,
    compute_migration_hash,
)
from app.core.openapi import add_error_responses
from app.core.permissions import require_workspace_permission
from app.models.ai_gene import AiGene
from app.models.base_class import BaseClass
from app.models.capability_market import (
    CapabilityCreatedVia,
    CapabilityMarketEntry,
    CapabilityType,
)
from app.models.entity import Entity
from app.models.instance import Instance
from app.models.memory import Memory
from app.schemas.learning import (
    AggregatedMemoryCount,
    CapabilityCandidateOut,
    CombineRequest,
    CombineResultOut,
    DistillRequest,
    DistillResultOut,
    MemorySummaryOut,
    PromoteRequest,
    PromoteResultOut,
    ReapRequest,
    ReapResultOut,
    SkillManifestPreview,
    TransmuteRequest,
    TransmuteResultOut,
)

router = APIRouter(prefix="/learning", tags=["Learning"])
add_error_responses(router)

# Slugify a free-form string into a kebab-case token safe for use as a
# capability name. Strips non-alphanumerics, collapses runs of hyphens,
# and trims leading/trailing hyphens. Capped at 200 chars to fit the
# DB column (255 minus a buffer).
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_REAP_DESC_CAP = 200
_MAX_COMMANDS_CANDIDATES = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_workspace_id_for_entity(db: DB, entity_id: str) -> str:
    """Return the workspace_id for the first Instance of *entity_id*.

    Raises NotFoundError if the entity has no instance (and thus no workspace).
    """
    result = await db.execute(
        select(Instance.workspace_id).where(
            Instance.entity_id == entity_id,
            Instance.deleted_at.is_(None),
        ).limit(1)
    )
    workspace_id = result.scalar_one_or_none()
    if workspace_id is None:
        raise NotFoundError(
            "entity.no_workspace",
            "errors.entity.no_workspace",
            f"Entity {entity_id!r} is not associated with any workspace",
        )
    return workspace_id


async def _get_first_instance_for_entity(
    db: DB, entity_id: str
) -> Instance | None:
    """Return the first active Instance of *entity_id* (or None)."""
    result = await db.execute(
        select(Instance)
        .where(
            Instance.entity_id == entity_id,
            Instance.deleted_at.is_(None),
        )
        .order_by(Instance.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _manifest_to_candidates(manifest: dict) -> list[CapabilityCandidate]:
    """Convert an LLM manifest dict into capability candidates.

    The LLM returns ``{commands, skills, tools, prompt, model}``; each list
    becomes market candidates typed by its list (command / skill / tool).
    ``prompt`` is carried as the skill candidates' ``config_template`` —
    a capability config, not a manifest embed. Candidates are deduplicated
    by name (upsert key) and capped like the heuristic engine.
    """
    candidates: list[CapabilityCandidate] = []
    seen: set[str] = set()
    prompt = manifest.get("prompt") or ""
    for name in (manifest.get("commands") or [])[:_MAX_COMMANDS_CANDIDATES]:
        if name and name not in seen:
            candidates.append(CapabilityCandidate(name=name, type="command"))
            seen.add(name)
    for name in (manifest.get("skills") or [])[:_MAX_COMMANDS_CANDIDATES]:
        if name and name not in seen:
            candidates.append(
                CapabilityCandidate(
                    name=name,
                    type="skill",
                    description=prompt or None,
                    config_template={"prompt": prompt} if prompt else None,
                )
            )
            seen.add(name)
    for name in (manifest.get("tools") or [])[:_MAX_COMMANDS_CANDIDATES]:
        if name and name not in seen:
            candidates.append(CapabilityCandidate(name=name, type="tool"))
            seen.add(name)
    return candidates


async def _result_from_llm_manifest(
    db: DB,
    entity_id: str,
    request: DistillRequest,
    manifest: dict,
) -> DistillResult:
    """Wrap an LLM manifest dict in a DistillResult (aggregation + candidates).

    Raises the standard ``learning.no_memory`` DistillationError when the
    entity has no memory entries, keeping the 422 contract across engines.
    """
    result = await db.execute(
        select(Memory).where(
            Memory.entity_id == entity_id,
            Memory.deleted_at.is_(None),
        )
    )
    entries = list(result.scalars().all())
    if not entries:
        raise DistillationError(
            code="learning.no_memory",
            message_key="errors.learning.no_memory",
            message="No memory entries for distillation",
        )
    skills = manifest.get("skills") or []
    return DistillResult(
        capability_candidates=_manifest_to_candidates(manifest),
        gene_suggestion=skills[0] if skills else None,
        aggregated_memory=aggregate_memory_counts(entries),
        source_entity_id=entity_id,
        source_preset_slug=request.source_preset_slug,
    )


# ---------------------------------------------------------------------------
# Memory summary
# ---------------------------------------------------------------------------


@router.get("/memories/{entity_id}/summary", response_model=MemorySummaryOut)
async def get_memory_summary(
    entity_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    kind: list[str] | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> MemorySummaryOut:
    """Return aggregated memory counts and sample data for an entity.

    Requires ``viewer`` role in the entity's workspace.
    Does **not** emit events (read-only).
    """
    # 1. Find Entity.
    emp = await db.get(Entity, entity_id)
    if emp is None or emp.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity {entity_id!r} not found",
        )

    # 2. Get workspace_id from entity's instance → check permission.
    workspace_id = await _get_workspace_id_for_entity(db, entity_id)
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )

    # 3. Aggregate counts by kind (direct SQL).
    count_q = (
        select(Memory.kind, func.count(Memory.id))
        .where(
            Memory.entity_id == entity_id,
            Memory.deleted_at.is_(None),
        )
        .group_by(Memory.kind)
    )
    if kind is not None:
        count_q = count_q.where(Memory.kind.in_(kind))

    count_result = await db.execute(count_q)
    kind_counter: dict[str, int] = {
        "experience": 0,
        "lesson": 0,
        "decision": 0,
        "problem": 0,
        "notepad": 0,
    }
    for row in count_result:
        kind_counter[row[0]] = row[1]

    total = sum(kind_counter.values())
    aggregated = AggregatedMemoryCount(
        experience=kind_counter["experience"],
        lesson=kind_counter["lesson"],
        decision=kind_counter["decision"],
        problem=kind_counter["problem"],
        notepad=kind_counter["notepad"],
        total=total,
    )

    # 4. Sample lessons (first <limit> lesson entries with non-empty content).
    #    Plan specifies first 5, but we use the query param for flexibility.
    sample_lessons_q = (
        select(Memory.content)
        .where(
            Memory.entity_id == entity_id,
            Memory.kind == "lesson",
            Memory.content.isnot(None),
            Memory.deleted_at.is_(None),
        )
        .order_by(Memory.created_at.asc())
        .limit(min(limit, 5))
    )
    lesson_result = await db.execute(sample_lessons_q)
    sample_lessons: list[str] = [row[0] for row in lesson_result if row[0]]

    # 5. Sample keys by kind (up to 5 per kind).
    keys_q = (
        select(Memory.kind, Memory.key)
        .where(
            Memory.entity_id == entity_id,
            Memory.key.isnot(None),
            Memory.deleted_at.is_(None),
        )
    )
    if kind is not None:
        keys_q = keys_q.where(Memory.kind.in_(kind))

    keys_result = await db.execute(keys_q)
    sample_keys_by_kind: dict[str, list[str]] = {}
    for row in keys_result:
        k_kind, k_key = row[0], row[1]
        if k_kind not in sample_keys_by_kind:
            sample_keys_by_kind[k_kind] = []
        if k_key and len(sample_keys_by_kind[k_kind]) < 5:
            sample_keys_by_kind[k_kind].append(k_key)

    return MemorySummaryOut(
        entity_id=entity_id,
        aggregated_counts=aggregated,
        sample_lessons=sample_lessons,
        sample_keys_by_kind=sample_keys_by_kind,
    )


# ---------------------------------------------------------------------------
# Distill
# ---------------------------------------------------------------------------


@router.post(
    "/entities/{entity_id}/distill",
    response_model=DistillResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def distill_entity(
    entity_id: str,
    body: DistillRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> DistillResultOut:
    """Distill an entity's memory into org-level capability_market entries.

    v4.9.3 炼化 chain: **distill = Entity memory → capability** (content
    chain source). Each distilled candidate is upserted into the
    capability_market with ``created_via="distill"`` (org scope) and its
    ``required_knowledge`` slug declaration; no BaseClass is created and
    no has_knowledge is attached (promote / transmute own that).

    ``engine=llm`` resolves an org provider for the entity's instance; when
    no provider is configured the request degrades to the heuristic engine
    and reports ``engine_used="heuristic"`` + a warning (never 422/500 on
    a missing provider).

    Requires ``editor`` role in the entity's workspace.
    Emits ``LEARNING_DISTILLATION_COMPLETED`` inside the transaction.
    """
    # 1. Find Entity.
    emp = await db.get(Entity, entity_id)
    if emp is None or emp.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity {entity_id!r} not found",
        )

    # 2. Permission check — editor in the entity's workspace.
    workspace_id = await _get_workspace_id_for_entity(db, entity_id)
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

    # 3. Resolve org scope for the market writes.
    from app.models.organization import Namespace

    ns = await db.get(Namespace, emp.namespace_id)
    entity_org_id = ns.org_id if ns is not None else None
    scope = "org" if entity_org_id else "system"

    # 4. Engine dispatch (Q5: engine=llm degrades to heuristic when the
    #    instance has no org provider configured).
    engine_used = body.engine
    warnings: list[str] = []
    try:
        if body.engine == "llm":
            instance = await _get_first_instance_for_entity(db, entity_id)
            provider = None
            model = None
            if instance is not None:
                from app.services.llm.instance_pi_env import (
                    resolve_provider_for_instance,
                )

                provider, model = await resolve_provider_for_instance(
                    db, instance.id
                )
            if provider is None:
                engine_used = "heuristic"
                warnings.append("llm_unavailable_degraded_to_heuristic")
                result = await AggregatingDistiller().distill(
                    entity_id, request=body, session=db
                )
            else:
                from app.services.llm.org_provider import (
                    build_llm_client_from_org_provider,
                )

                llm_client = build_llm_client_from_org_provider(
                    provider, model=model
                )
                manifest = await LLMDistiller(llm_client).distill(
                    entity_id, session=db
                )
                result = await _result_from_llm_manifest(
                    db, entity_id, body, manifest
                )
        else:
            result = await AggregatingDistiller().distill(
                entity_id, request=body, session=db
            )
    except DistillationError as exc:
        if exc.code == "entity.not_found":
            raise NotFoundError(exc.code, exc.message_key, exc.message) from exc
        raise ValidationError(exc.code, exc.message_key, exc.message) from exc

    # 5. Persist candidates to capability_market (idempotent by name).
    candidate_names = [c.name for c in result.capability_candidates]
    existing_names: set[str] = set()
    if candidate_names:
        market_q = await db.execute(
            select(CapabilityMarketEntry.name).where(
                CapabilityMarketEntry.name.in_(candidate_names),
                CapabilityMarketEntry.deleted_at.is_(None),
            )
        )
        existing_names = {row[0] for row in market_q}

    created_caps: list[CapabilityCandidateOut] = []
    created_count = 0
    for cand in result.capability_candidates:
        market = await upsert_capability(
            db,
            name=cand.name,
            cap_type=cand.type,
            scope=scope,
            organization_id=entity_org_id,
            created_via=CapabilityCreatedVia.distill.value,
            description=cand.description,
            config_template=cand.config_template,
            required_knowledge=cand.required_knowledge,
            source_entity_slug=emp.slug,
        )
        if cand.name not in existing_names:
            created_count += 1
            existing_names.add(cand.name)
        created_caps.append(
            CapabilityCandidateOut(
                id=market.id,
                name=market.name,
                type=market.type,
                description=market.description,
                config_template=market.config_template,
                required_knowledge=market.required_knowledge or [],
                created_via=market.created_via,
            )
        )

    # 6. Emit event within the same transaction.
    await emit(
        LEARNING_DISTILLATION_COMPLETED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="capability_market",
        resource_id=entity_id,
        payload={
            "entity_id": entity_id,
            "capabilities_count": len(created_caps),
            "capability_market_created": created_count,
            "gene_suggestion": result.gene_suggestion,
            "engine_used": engine_used,
            "aggregated_counts": {
                "experience": result.aggregated_memory.experience,
                "lesson": result.aggregated_memory.lesson,
                "decision": result.aggregated_memory.decision,
                "problem": result.aggregated_memory.problem,
                "notepad": result.aggregated_memory.notepad,
                "total": result.aggregated_memory.total,
            },
        },
        session=db,
    )

    # 7. Commit.
    await db.commit()

    return DistillResultOut(
        capability_candidates=created_caps,
        capability_market_created=created_count,
        gene_suggestion=result.gene_suggestion,
        engine_used=engine_used,
        warnings=warnings,
        aggregated_memory=result.aggregated_memory,
        source_entity_id=entity_id,
        source_preset_slug=result.source_preset_slug,
    )


# ---------------------------------------------------------------------------
# Preset fetch (historical distill results)
# ---------------------------------------------------------------------------


@router.get("/presets/{preset_id}", response_model=DistillResultOut)
async def get_learning_preset(
    preset_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> DistillResultOut:
    """Fetch a previously distilled preset by its UUID.

    Returns the distill result with manifest preview.
    Does **not** require workspace membership — any authenticated user can view.
    """
    preset = await db.get(BaseClass, preset_id)
    if preset is None or preset.deleted_at is not None:
        raise NotFoundError(
            "base_class.not_found",
            "errors.base_class.not_found",
            f"BaseClass {preset_id!r} not found",
        )

    manifest_data = preset.manifest if isinstance(preset.manifest, dict) else {}
    manifest_preview = SkillManifestPreview.model_validate(manifest_data)

    source_preset_slug: str | None = None
    if isinstance(preset.manifest, dict):
        source_preset_slug = preset.manifest.get("source_preset_slug")

    return DistillResultOut(
        new_preset_id=preset.id,
        new_preset_slug=preset.slug,
        new_preset_name=preset.name,
        manifest_preview=manifest_preview,
        aggregated_memory=AggregatedMemoryCount(),
        source_entity_id="",
        source_preset_slug=source_preset_slug,
    )


# ---------------------------------------------------------------------------
# Phase-15f capability lifecycle (PRD §13.6.3–§13.6.5)
# ---------------------------------------------------------------------------


def _slugify_capability_name(text: str) -> str:
    """Convert *text* into a kebab-case capability slug.

    Lower-cases, replaces runs of non-alphanumerics with single hyphens,
    and trims leading/trailing hyphens. Falls back to ``"capability"`` if
    the input contains no alphanumerics.
    """
    lowered = text.lower().strip()
    slug = _SLUG_NON_ALNUM.sub("-", lowered).strip("-")
    if not slug:
        return "capability"
    return slug[:200]


def _truncate_for_description(text: str, max_chars: int = _REAP_DESC_CAP) -> str:
    """Truncate *text* to *max_chars*, appending ``"..."`` if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


# ---------------------------------------------------------------------------
# Endpoint A: POST /learning/instances/{iid}/reap
# ---------------------------------------------------------------------------


@router.post("/instances/{instance_id}/reap", response_model=ReapResultOut)
async def reap_instance(
    instance_id: str,
    body: ReapRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> ReapResultOut:
    """Reap reusable capabilities from an instance's Memory log.

    v4.9.3 炼化 chain division: **reap = Instance-level memory → capability
    draft**; the Entity row is NOT mutated (``entity_changed: false``).
    Distilled drafts are promoted to the Entity by ``promote`` and
    settled into the org market by ``distill`` — the three endpoints never
    overlap: reap (draft) / promote (Instance→Entity) / distill (Entity→market).

    Per PRD §13.6.3: distil memory entries into capability dicts, write
    them to the L1 capability_market (via ``created_via="reap"``) and to
    the instance's local runtime_config.
    """
    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance {instance_id!r} not found",
        )

    entity = await db.get(Entity, instance.entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity {instance.entity_id!r} not found",
        )

    await require_workspace_permission(
        db,
        current_user.user_id,
        instance.workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )

    # 1. Pull memory entries visible to this instance.
    mem_q = (
        select(Memory)
        .where(
            Memory.deleted_at.is_(None),
            (Memory.source_instance_id == instance_id)
            | (Memory.entity_id == instance.entity_id),
        )
        .order_by(Memory.created_at.asc())
        .limit(body.max_capabilities)
    )
    if body.memory_kind_filter:
        mem_q = mem_q.where(Memory.kind.in_(body.memory_kind_filter))

    mem_rows = (await db.execute(mem_q)).scalars().all()
    memory_consumed = len(mem_rows)

    # 2. Distil — deterministic, no LLM. Each memory → one capability.
    distilled: list[dict] = []
    for entry in mem_rows:
        seed_text = entry.key or entry.content or entry.kind
        cap_name = _slugify_capability_name(seed_text)
        description = _truncate_for_description(entry.content or entry.key or entry.kind)
        distilled.append({
            "name": cap_name,
            "type": CapabilityType.skill.value,
            "description": description,
            "tags": ["auto-distilled"],
            "source_kind": entry.kind,
            "source_memory_id": entry.id,
        })

    # 3. snapshot_only → return preview without writing.
    if body.snapshot_only:
        return ReapResultOut(
            reaped_at=datetime.now(timezone.utc).isoformat(),
            instance_id=instance_id,
            memory_consumed=memory_consumed,
            capability_distilled=distilled,
            capability_market_uploaded=0,
            instance_local_added=0,
            entity_changed=False,
        )

    # 4. Write to capability_market (idempotent by name).
    market_uploaded = 0
    existing_names: set[str] = set()
    if distilled:
        market_q = await db.execute(
            select(CapabilityMarketEntry.name).where(
                CapabilityMarketEntry.name.in_([c["name"] for c in distilled]),
                CapabilityMarketEntry.deleted_at.is_(None),
            )
        )
        existing_names = {row[0] for row in market_q}

    for cap in distilled:
        if cap["name"] in existing_names:
            continue
        market_entry = CapabilityMarketEntry(
            name=cap["name"],
            type=cap["type"],
            description=cap["description"],
            tags=cap["tags"],
            created_via=CapabilityCreatedVia.reap.value,
            source_entity_slug=entity.slug,
        )
        db.add(market_entry)
        existing_names.add(cap["name"])
        market_uploaded += 1

    # 5. Write to instance runtime_config["reaped_capabilities"] (append).
    runtime_config = dict(instance.runtime_config or {})
    existing_reaped = list(runtime_config.get("reaped_capabilities", []))
    for cap in distilled:
        if cap["name"] not in {c.get("name") for c in existing_reaped}:
            existing_reaped.append(cap)
    runtime_config["reaped_capabilities"] = existing_reaped
    instance.runtime_config = runtime_config

    # 6. Emit event within transaction.
    await emit(
        LEARNING_REAPED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="instance",
        resource_id=instance.id,
        payload={
            "instance_id": instance_id,
            "memory_consumed": memory_consumed,
            "capabilities_count": len(distilled),
            "capability_market_uploaded": market_uploaded,
        },
        session=db,
    )

    await db.commit()

    return ReapResultOut(
        reaped_at=datetime.now(timezone.utc).isoformat(),
        instance_id=instance_id,
        memory_consumed=memory_consumed,
        capability_distilled=distilled,
        capability_market_uploaded=market_uploaded,
        instance_local_added=len(distilled),
        entity_changed=False,
    )


# ---------------------------------------------------------------------------
# Endpoint B: POST /learning/entities/{eid}/promote
# ---------------------------------------------------------------------------


@router.post("/entities/{entity_id}/promote", response_model=PromoteResultOut)
async def promote_entity(
    entity_id: str,
    body: PromoteRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> PromoteResultOut:
    """Promote an instance's capability set into the Entity (回魂) or fork a new Entity (派生)."""
    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity {entity_id!r} not found",
        )

    if body.mode == "fork":
        if not body.new_entity_name or not body.new_entity_slug:
            raise ValidationError(
                "promote.fork_fields_required",
                "errors.promote.fork_fields_required",
                "new_entity_name and new_entity_slug are required when mode=fork",
            )
        slug_clash = await db.execute(
            select(Entity).where(
                Entity.namespace_id == entity.namespace_id,
                Entity.slug == body.new_entity_slug,
                Entity.deleted_at.is_(None),
            )
        )
        if slug_clash.scalar_one_or_none() is not None:
            raise ConflictError(
                "entity.slug_taken",
                "errors.entity.slug_taken",
                f"Entity slug '{body.new_entity_slug}' already taken in namespace",
            )

    # 1. Resolve source instance.
    if body.from_instance_id:
        instance = await db.get(Instance, body.from_instance_id)
        if instance is None or instance.deleted_at is not None:
            raise NotFoundError(
                "instance.not_found",
                "errors.instance.not_found",
                f"Instance {body.from_instance_id!r} not found",
            )
        if instance.entity_id != entity_id:
            raise ValidationError(
                "instance.entity_mismatch",
                "errors.instance.entity_mismatch",
                "Instance does not belong to the given Entity",
            )
    else:
        result = await db.execute(
            select(Instance)
            .where(
                Instance.entity_id == entity_id,
                Instance.deleted_at.is_(None),
            )
            .order_by(Instance.created_at.asc())
            .limit(1)
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            raise NotFoundError(
                "entity.no_instance",
                "errors.entity.no_instance",
                f"Entity {entity_id!r} has no active instance",
            )

    await require_workspace_permission(
        db,
        current_user.user_id,
        instance.workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

    # 2. Compute instance's effective capability set (v4.0: junction is truth).
    from app.core.capabilities import (
        attach_entity_capability,
        load_entity_capability_dicts,
        upsert_capability,
    )

    existing_caps = await load_entity_capability_dicts(db, entity.id)
    instance_runtime = instance.runtime_config or {}
    reaped_caps = list(instance_runtime.get("reaped_capabilities", []))
    if not reaped_caps:
        reaped_caps = list(existing_caps)

    # 3. Build idempotent union.
    existing_names = {c.get("name") for c in existing_caps if c.get("name")}
    promoted_now = 0
    merged = list(existing_caps)
    new_caps: list[dict] = []
    for cap in reaped_caps:
        name = cap.get("name") if isinstance(cap, dict) else None
        if not name or name in existing_names:
            continue
        merged.append(cap)
        new_caps.append(cap)
        existing_names.add(name)
        promoted_now += 1

    # 3b. v4.9.3 has-knowledge aggregate — union of the Entity's current
    #     knowledge and the source instance's runtime_config knowledge env
    #     keys (化身→眷族 direction). Atomic with the capability writes.
    knowledge_env = (instance_runtime.get("knowledge") or {}).get("env") or {}
    env_keys = {str(k) for k in knowledge_env.keys() if k}
    has_knowledge_aggregate = sorted(set(entity.has_knowledge or []) | env_keys)

    # 4. Decide prompt snapshot (prefer Entity.system_prompt overlay).
    prompt_regen = entity.system_prompt
    if body.include_prompt_regen:
        seed = hashlib.sha256(
            (entity.slug + "|" + ",".join(sorted(existing_names))).encode("utf-8"),
        ).hexdigest()[:12]
        prompt_regen = (
            f"你是眷族「{entity.name}」，由炼化晋升而来（seed={seed}）。"
            f"已接入能力：{', '.join(sorted(existing_names))}。"
        )

    # 5. snapshot_only → preview without writing.
    if body.snapshot_only:
        return PromoteResultOut(
            mode=body.mode,
            promoted_at=datetime.now(timezone.utc).isoformat(),
            entity_id=entity_id,
            entity_promotion_migration_hash=compute_migration_hash(
                merged, prompt_regen,
            ),
            capability_promoted_count=promoted_now,
            prompt_regenerated=body.include_prompt_regen,
            new_prompt_preview=prompt_regen or "",
            outdated_instances_count=0,
            capability_market_uploaded=0,
            has_knowledge=has_knowledge_aggregate,
        )

    if body.mode == "fork":
        new_entity = Entity(
            namespace_id=entity.namespace_id,
            name=body.new_entity_name,
            slug=body.new_entity_slug,
            preset_slug=entity.preset_slug,
            rank=entity.rank,
            display_name=body.new_entity_name,
            display_color=entity.display_color,
            system_prompt=prompt_regen if body.include_prompt_regen else entity.system_prompt,
            config_override=entity.config_override,
            has_knowledge=has_knowledge_aggregate,
        )
        db.add(new_entity)
        await db.flush()
        # v4.0 §6.4: fork copies the merged capability set via junction rows.
        from app.models.organization import Namespace

        ns = await db.get(Namespace, entity.namespace_id)
        fork_org_id = ns.org_id if ns is not None else None
        for cap in merged:
            name = cap.get("name") if isinstance(cap, dict) else None
            if not name:
                continue
            market = await upsert_capability(
                db,
                name=name,
                cap_type=cap.get("type") or "skill",
                scope="org" if fork_org_id else "system",
                organization_id=fork_org_id,
                created_via="promote",
                description=cap.get("description"),
                config_template=cap.get("config_template") or cap.get("config"),
                source_entity_slug=entity.slug,
            )
            await attach_entity_capability(
                db, entity_id=new_entity.id, capability_id=market.id
            )
        new_migration_hash = await compute_entity_migration_hash(db, new_entity)
        new_entity.migration_hash = new_migration_hash

        await emit(
            LEARNING_PROMOTED,
            actor_type="user",
            actor_id=current_user.user_id,
            resource_type="entity",
            resource_id=new_entity.id,
            payload={
                "mode": "fork",
                "source_entity_id": entity_id,
                "entity_id": new_entity.id,
                "new_migration_hash": new_migration_hash,
                "capability_promoted_count": promoted_now,
            },
            session=db,
        )
        await db.commit()
        return PromoteResultOut(
            mode="fork",
            promoted_at=datetime.now(timezone.utc).isoformat(),
            entity_id=entity_id,
            new_entity_id=new_entity.id,
            entity_promotion_migration_hash=new_migration_hash,
            capability_promoted_count=promoted_now,
            prompt_regenerated=body.include_prompt_regen,
            new_prompt_preview=prompt_regen or "",
            outdated_instances_count=0,
            capability_market_uploaded=0,
            has_knowledge=has_knowledge_aggregate,
        )

    # 6. Persist via junction (v4.0 §6.4 — JSONB write path removed).
    from app.models.organization import Namespace

    ns = await db.get(Namespace, entity.namespace_id)
    entity_org_id = ns.org_id if ns is not None else None
    for cap in new_caps:
        market = await upsert_capability(
            db,
            name=cap["name"],
            cap_type=cap.get("type") or "skill",
            scope="org" if entity_org_id else "system",
            organization_id=entity_org_id,
            created_via="promote",
            description=cap.get("description"),
            config_template=cap.get("config_template") or cap.get("config"),
            source_entity_slug=entity.slug,
        )
        await attach_entity_capability(
            db, entity_id=entity.id, capability_id=market.id
        )
    if body.include_prompt_regen and prompt_regen:
        entity.system_prompt = prompt_regen
    entity.has_knowledge = has_knowledge_aggregate
    new_migration_hash = await compute_entity_migration_hash(db, entity)
    entity.migration_hash = new_migration_hash

    market_uploaded = 0

    # 7. Count outdated instances (excluding the source instance).
    sibling_q = (
        select(Instance)
        .where(
            Instance.entity_id == entity_id,
            Instance.id != instance.id,
            Instance.deleted_at.is_(None),
        )
    )
    siblings = (await db.execute(sibling_q)).scalars().all()
    outdated_count = sum(
        1 for s in siblings if s.active_hash != new_migration_hash
    )

    # 8. Emit event.
    await emit(
        LEARNING_PROMOTED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="entity",
        resource_id=entity.id,
        payload={
            "mode": "update",
            "entity_id": entity_id,
            "new_migration_hash": new_migration_hash,
            "capability_promoted_count": promoted_now,
            "outdated_instances_count": outdated_count,
        },
        session=db,
    )

    await db.commit()

    return PromoteResultOut(
        mode="update",
        promoted_at=datetime.now(timezone.utc).isoformat(),
        entity_id=entity_id,
        entity_promotion_migration_hash=new_migration_hash,
        capability_promoted_count=promoted_now,
        prompt_regenerated=body.include_prompt_regen,
        new_prompt_preview=prompt_regen or "",
        outdated_instances_count=outdated_count,
        capability_market_uploaded=market_uploaded,
        has_knowledge=has_knowledge_aggregate,
    )


# ---------------------------------------------------------------------------
# Endpoint C: POST /learning/entities/{eid}/distill?action=transmute
# ---------------------------------------------------------------------------


@router.post(
    "/entities/{entity_id}/transmute",
    response_model=TransmuteResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def transmute_entity(
    entity_id: str,
    body: TransmuteRequest,
    db: DB = None,
    current_user: CurrentUserDep = None,
    x_organization_id: XOrgIdHeader = None,
) -> TransmuteResultOut:
    """Distill an Entity into a new BaseClass (L3 神职).

    Per PRD §13.6.5: pure derivative operation. The source Entity is
    NOT mutated and capability_market is NOT touched. Only the new
    BaseClass row is created.
    """
    entity = await db.get(Entity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise NotFoundError(
            "entity.not_found",
            "errors.entity.not_found",
            f"Entity {entity_id!r} not found",
        )

    # Find an workspace for the entity to scope auth.
    inst_q = await db.execute(
        select(Instance.workspace_id).where(
            Instance.entity_id == entity_id,
            Instance.deleted_at.is_(None),
        ).limit(1)
    )
    workspace_id = inst_q.scalar_one_or_none()
    if workspace_id is None:
        raise NotFoundError(
            "entity.no_workspace",
            "errors.entity.no_workspace",
            f"Entity {entity_id!r} is not associated with any workspace",
        )

    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

    # 1. Build the new manifest (v4.0: capability truth is the junction;
    #    v4.9.3: default_gene_refs come from the Entity's attached genes).
    from app.core.capabilities import (
        attach_base_class_ai_gene,
        attach_base_class_capability,
        load_entity_ai_gene_dicts,
        load_entity_capability_dicts,
        upsert_capability,
    )
    from app.models.organization import Namespace

    entity_caps = await load_entity_capability_dicts(db, entity.id)
    gene_refs = [
        g["slug"] for g in await load_entity_ai_gene_dicts(db, entity)
        if g.get("slug")
    ]
    entity_has_knowledge = sorted(set(entity.has_knowledge or []))
    ns = await db.get(Namespace, entity.namespace_id)
    entity_org_id = ns.org_id if ns is not None else None
    manifest = {
        "provider_config": {},
        "default_model": "tbd",
        "commands": [],
        "default_capabilities": list(entity_caps),
        "default_gene_refs": list(gene_refs),
        "has_knowledge": entity_has_knowledge,
        "system_prompt": entity.system_prompt or "",
    }

    # 2. Slug uniqueness check.
    existing_q = await db.execute(
        select(BaseClass).where(
            BaseClass.slug == body.target_base_class_slug,
            BaseClass.deleted_at.is_(None),
        )
    )
    if existing_q.scalar_one_or_none() is not None:
        raise ConflictError(
            "base_class.slug_taken",
            "errors.base_class.slug_taken",
            f"BaseClass slug {body.target_base_class_slug!r} is already taken",
        )

    # 3. snapshot_only → preview without writing.
    if body.snapshot_only:
        return TransmuteResultOut(
            new_base_class_id="",
            new_base_class_slug=body.target_base_class_slug,
            new_base_class_name=body.target_base_class_name,
            manifest_preview=manifest,
            source_entity_id=entity_id,
            default_gene_refs=list(gene_refs),
            has_knowledge=entity_has_knowledge,
        )

    # 4. Create BaseClass (org scope) + base_class_capabilities junction
    #    (§6.4) + base_class_ai_genes junction + has_knowledge mount.
    new_bc = BaseClass(
        slug=body.target_base_class_slug,
        name=body.target_base_class_name,
        manifest=manifest,
        scope="org" if entity_org_id else "system",
        organization_id=entity_org_id,
        version="0.1.0",
        has_knowledge=entity_has_knowledge,
    )
    db.add(new_bc)
    await db.flush()
    for cap in entity_caps:
        name = cap.get("name")
        if not name:
            continue
        market = await upsert_capability(
            db,
            name=name,
            cap_type=cap.get("type") or "skill",
            scope="org" if entity_org_id else "system",
            organization_id=entity_org_id,
            created_via="manual",
            description=cap.get("description"),
            config_template=cap.get("config_template") or cap.get("config"),
        )
        await attach_base_class_capability(
            db, base_class_id=new_bc.id, capability_id=market.id
        )
    if gene_refs:
        gene_q = await db.execute(
            select(AiGene).where(
                AiGene.slug.in_(gene_refs),
                AiGene.deleted_at.is_(None),
            )
        )
        for gene in gene_q.scalars().all():
            await attach_base_class_ai_gene(
                db, base_class_id=new_bc.id, ai_gene_id=gene.id
            )

    # 5. Emit event.
    await emit(
        LEARNING_TRANSMUTED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="base_class",
        resource_id=new_bc.id,
        payload={
            "source_entity_id": entity_id,
            "new_base_class_slug": new_bc.slug,
            "capability_count": len(manifest["default_capabilities"]),
        },
        session=db,
    )

    await db.commit()
    await db.refresh(new_bc)

    return TransmuteResultOut(
        new_base_class_id=new_bc.id,
        new_base_class_slug=new_bc.slug,
        new_base_class_name=new_bc.name,
        manifest_preview=manifest,
        source_entity_id=entity_id,
        default_gene_refs=list(gene_refs),
        has_knowledge=entity_has_knowledge,
    )


# ---------------------------------------------------------------------------
# Endpoint D: POST /learning/capabilities/combine
# ---------------------------------------------------------------------------


@router.post(
    "/capabilities/combine",
    response_model=CombineResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def combine_capabilities(
    body: CombineRequest,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> CombineResultOut:
    """Package N L1 capabilities into a single L2 Gene (AiGene).

    Per PRD §13.6.10.2.2: all referenced capability names must exist in
    the capability_market (otherwise 404). The new gene references them
    by name in its manifest.

    v4.6 §6.4: optional ``entity_id`` / ``base_class_id`` binding writes
    ``entity_ai_genes`` / ``base_class_ai_genes`` junctions. Both targets
    are validated (existence + ``can_manage_ai_genes`` on their scope)
    **before** the snapshot_only branch so preview and write modes behave
    identically — no DB write precedes validation.
    """
    # 1. Validate all referenced capabilities exist.
    cap_q = await db.execute(
        select(CapabilityMarketEntry).where(
            CapabilityMarketEntry.name.in_(body.capability_names),
            CapabilityMarketEntry.deleted_at.is_(None),
        )
    )
    found = {c.name: c for c in cap_q.scalars().all()}
    missing = [n for n in body.capability_names if n not in found]
    if missing:
        raise NotFoundError(
            "capability.not_found",
            "errors.capability.not_found",
            f"Capability(s) not found: {missing}",
            details={"missing": missing},
        )

    # 2. Build manifest preview.
    from app.core.capabilities import build_capabilities_manifest

    manifest = {
        "capabilities": build_capabilities_manifest(
            [found[n] for n in body.capability_names]
        ),
        "tools": [],
        "scripts": {},
        "runtime_config": {},
    }

    # 3. Slug uniqueness check.
    existing_gene = await db.execute(
        select(AiGene).where(
            AiGene.slug == body.gene_slug,
            AiGene.deleted_at.is_(None),
        )
    )
    if existing_gene.scalar_one_or_none() is not None:
        raise ConflictError(
            "ai_gene.slug_taken",
            "errors.ai_gene.slug_taken",
            f"AiGene slug {body.gene_slug!r} is already taken",
        )

    # 4. v4.6 review fix: validate binding targets exist + the caller holds
    #    can_manage_ai_genes on the target scope (mirrors the v4.1 ai-genes /
    #    entities / base-classes gene-attach endpoints) — before snapshot_only
    #    so preview and write paths validate identically.
    from app.core.permissions import require_permission

    entity_target: Entity | None = None
    base_class_target: BaseClass | None = None
    if body.entity_id:
        entity_target = await db.get(Entity, body.entity_id)
        if entity_target is None or entity_target.deleted_at is not None:
            raise NotFoundError(
                "entity.not_found",
                "errors.entity.not_found",
                f"Entity {body.entity_id!r} not found",
            )
        await require_permission(
            db,
            current_user.user_id,
            "can_manage_ai_genes",
            namespace_id=entity_target.namespace_id,
        )
    if body.base_class_id:
        base_class_target = await db.get(BaseClass, body.base_class_id)
        if base_class_target is None or base_class_target.deleted_at is not None:
            raise NotFoundError(
                "base_class.not_found",
                "errors.base_class.not_found",
                f"BaseClass {body.base_class_id!r} not found",
            )
        # Unconditional, mirroring base_classes.py attach_base_class_ai_gene_route:
        # system-scope presets resolve to a root grant check (super-admin only).
        await require_permission(
            db,
            current_user.user_id,
            "can_manage_ai_genes",
            organization_id=base_class_target.organization_id,
            namespace_id=base_class_target.namespace_id,
        )

    # 5. snapshot_only → preview without writing.
    if body.snapshot_only:
        return CombineResultOut(
            new_gene_id="",
            new_gene_slug=body.gene_slug,
            referenced_capabilities=list(body.capability_names),
            manifest_preview=manifest,
            entity_id=body.entity_id,
            base_class_id=body.base_class_id,
        )

    # 6. Create AiGene.
    new_gene = AiGene(
        slug=body.gene_slug,
        name=body.gene_name,
        tags=body.tags or [],
        manifest=manifest,
    )
    db.add(new_gene)
    await db.flush()

    # 7. v4.6 §6.4: 组合后按产品选择绑定层 — entity_ai_genes / base_class_ai_genes。
    from app.core.capabilities import (
        attach_base_class_ai_gene,
        attach_entity_ai_gene,
    )

    if entity_target is not None:
        await attach_entity_ai_gene(
            db, entity_id=entity_target.id, ai_gene_id=new_gene.id
        )
    if base_class_target is not None:
        await attach_base_class_ai_gene(
            db, base_class_id=base_class_target.id, ai_gene_id=new_gene.id
        )

    # 8. Emit event.
    await emit(
        LEARNING_COMPOSED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="ai_gene",
        resource_id=new_gene.id,
        payload={
            "gene_slug": body.gene_slug,
            "referenced_capabilities": list(body.capability_names),
            "entity_id": body.entity_id,
            "base_class_id": body.base_class_id,
        },
        session=db,
    )

    await db.commit()
    await db.refresh(new_gene)

    return CombineResultOut(
        new_gene_id=new_gene.id,
        new_gene_slug=new_gene.slug,
        referenced_capabilities=list(body.capability_names),
        manifest_preview=manifest,
        entity_id=body.entity_id,
        base_class_id=body.base_class_id,
    )
