"""Directive routing engine.

Routes parsed Turn directives to target entities via passage-gated delivery.
Chains parse_turn → route_message per directive → trigger_on_mention on success.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.activation import trigger_on_mention
from app.core.message_router import MessageDeliveryResult, route_message
from app.core.preset_registry import is_control_command, is_learning_command
from app.core.slash_parser import parse_turn
from app.models.entity import Entity
from app.models.workspace import Membership
from app.schemas.slash import Directive


@dataclass
class DirectiveResult:
    directive_raw: str
    target_entity: str | None
    cmd: str | None
    results: list[MessageDeliveryResult] = field(default_factory=list)
    # v4.9.3: distill semantics report the created capability_market rows
    # plus which engine produced them (heuristic by default).
    created_capabilities: list[dict[str, Any]] = field(default_factory=list)
    engine_used: str = "heuristic"


# v4.9.3 distill helpers — Entity memory → capability_market candidates.
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_DESC_CAP = 200


def _slugify_capability_name(text: str) -> str:
    """Kebab-case capability slug from arbitrary memory text."""
    slug = _SLUG_NON_ALNUM.sub("-", text.lower().strip()).strip("-")
    if not slug:
        return "capability"
    return slug[:200]


def _knowledge_slugs_for_memory(key: str | None) -> list[str] | None:
    """Required-knowledge slugs a memory-derived capability declares.

    v4.9.3: require-knowledge keys are capability/gene slugs (== Instance
    env keys). Heuristically, the first hyphen-delimited segment of the
    memory key names the topic the capability needs to know about.
    """
    if not key:
        return None
    prefix = key.split("-")[0].strip().lower()
    return [prefix] if prefix else None


async def _distill_memory_candidates(
    session: AsyncSession,
    entity_id: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Entity memory → capability candidates (v4.9.3 distill semantics).

    Deterministic heuristic (no LLM): each active memory entry becomes one
    skill-type capability candidate carrying the required-knowledge slugs
    derived from its key. Mirrors the reap endpoint's memory→capability
    mapping; persistence is the caller's job (``upsert_capability`` with
    ``created_via="distill"``).
    """
    from app.models.memory import Memory

    result = await session.execute(
        select(Memory)
        .where(
            Memory.entity_id == entity_id,
            Memory.deleted_at.is_(None),
        )
        .order_by(Memory.created_at.asc())
        .limit(limit)
    )
    candidates: list[dict[str, Any]] = []
    for entry in result.scalars().all():
        seed_text = entry.key or entry.content or entry.kind
        description = (entry.content or entry.key or entry.kind)[:_DESC_CAP]
        candidates.append(
            {
                "name": _slugify_capability_name(seed_text),
                "type": "skill",
                "description": description,
                "required_knowledge": _knowledge_slugs_for_memory(entry.key),
            }
        )
    return candidates


async def route_turn(
    session: AsyncSession,
    raw_text: str,
    workspace_id: str,
    from_user_id: str,
) -> list[DirectiveResult]:
    """Parse a turn and route each directive to its target entity.

    1. Parse raw_text into a Turn via P4's parse_turn
    2. Find the sender's Membership in this workspace
    3. For each directive:
       a. Route via message_router
       b. On successful delivery, trigger on_mention activation
    4. Return per-directive results
    """
    turn = parse_turn(raw_text)

    # Find the sender's membership
    result = await session.execute(
        select(Membership).where(
            Membership.user_id == from_user_id,
            Membership.workspace_id == workspace_id,
            Membership.deleted_at.is_(None),
        )
    )
    sender_membership = result.scalars().first()
    if sender_membership is None:
        return []  # Sender not a member of this workspace

    directive_results: list[DirectiveResult] = []

    for directive in turn.directives:
        target_slug = directive.target_entity

        # CONTROL COMMAND BRANCH (P8) — routes to Harness Supervisor, NOT passage
        # Bare cmds (target_slug is None) are silently dropped, matching P5 contract.
        if is_control_command(directive.cmd):
            directive_results.append(
                await _route_control_directive(
                    session=session,
                    workspace_id=workspace_id,
                    directive=directive,
                    target_slug=target_slug,
                )
            )
            continue

        # LEARNING COMMAND BRANCH (P10) — routes to AggregatingDistiller,
        # NOT passage. Requires explicit @target; bare cmds are silently
        # dropped, matching P5 bare-cmd semantics.
        if is_learning_command(directive.cmd):
            directive_results.append(
                await _route_learning_directive(
                    session=session,
                    workspace_id=workspace_id,
                    directive=directive,
                    target_slug=target_slug,
                    from_user_id=from_user_id,
                )
            )
            continue

        # Resolve target Entity for on_mention triggering (v5.0: no intern hot-load).
        target_entity = None
        if target_slug:
            result = await session.execute(
                select(Entity).where(
                    Entity.slug == target_slug,
                    Entity.deleted_at.is_(None),
                )
            )
            target_entity = result.scalars().first()

            # v5.0 T4: No-instance guard — reject @mentions for entities
            # that have no active Instance in this workspace.
            if target_entity is not None:
                from app.models.instance import Instance, InstanceStatus

                inst_result = await session.execute(
                    select(Instance).where(
                        Instance.entity_id == target_entity.id,
                        Instance.workspace_id == workspace_id,
                        Instance.deleted_at.is_(None),
                        Instance.status.in_(
                            [
                                InstanceStatus.running.value,
                                InstanceStatus.pending.value,
                                InstanceStatus.creating.value,
                                InstanceStatus.deploying.value,
                            ]
                        ),
                    )
                )
                existing_instance = inst_result.scalars().first()
                if existing_instance is None:
                    directive_results.append(
                        DirectiveResult(
                            directive_raw=directive.raw_text,
                            target_entity=target_slug,
                            cmd=directive.cmd,
                            results=[],
                        )
                    )
                    continue

        # Route the directive
        delivery_results = await route_message(
            session=session,
            from_membership_id=sender_membership.id,
            workspace_id=workspace_id,
            directive=directive,
            general_text=turn.general_text,
        )

        # Trigger on_mention for successful deliveries
        for result_obj in delivery_results:
            if result_obj.delivered and target_entity:
                await trigger_on_mention(
                    session=session,
                    entity_id=target_entity.id,
                    workspace_id=workspace_id,
                )

        directive_results.append(
            DirectiveResult(
                directive_raw=directive.raw_text,
                target_entity=target_slug,
                cmd=directive.cmd,
                results=delivery_results,
            )
        )

    return directive_results


async def _route_control_directive(
    session: AsyncSession,
    workspace_id: str,
    directive: Directive,
    target_slug: str | None,
) -> DirectiveResult:
    """Route a control command to the Harness Supervisor.

    Bare cmds (target_slug is None) are silently dropped — matching the P5
    bare-cmd semantics in ``app/core/message_router.py:93-94``. With an
    explicit @target, we look up the target Entity's active Instance in
    this workspace and dispatch to the corresponding Supervisor action.

    Returns a ``DirectiveResult`` with the cmd echoed and an empty results
    list (control commands don't produce ``MessageDeliveryResult`` rows;
    their effect is on the harness state, not the message log).
    """
    if target_slug is None:
        # Bare cmd — silently drop per P5 bare-cmd semantics
        return DirectiveResult(
            directive_raw=directive.raw_text,
            target_entity=None,
            cmd=directive.cmd,
            results=[],
        )

    emp_result = await session.execute(
        select(Entity).where(
            Entity.slug == target_slug,
            Entity.deleted_at.is_(None),
        )
    )
    target_entity = emp_result.scalars().first()
    if target_entity is None:
        return DirectiveResult(
            directive_raw=directive.raw_text,
            target_entity=target_slug,
            cmd=directive.cmd,
            results=[],
        )

    from app.models.instance import Instance, InstanceStatus

    inst_result = await session.execute(
        select(Instance).where(
            Instance.entity_id == target_entity.id,
            Instance.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
            Instance.status.in_(
                [
                    InstanceStatus.running.value,
                    InstanceStatus.pending.value,
                    InstanceStatus.creating.value,
                    InstanceStatus.deploying.value,
                ]
            ),
        )
    )
    instance = inst_result.scalars().first()
    if instance is None:
        return DirectiveResult(
            directive_raw=directive.raw_text,
            target_entity=target_slug,
            cmd=directive.cmd,
            results=[],
        )

    from app.core.harness_supervisor import supervisor

    if directive.cmd == "/interrupt":
        await supervisor.handle_interrupt(instance.id, session)
    elif directive.cmd == "/pause":
        await supervisor.handle_pause(instance.id, session)
    elif directive.cmd == "/resume":
        await supervisor.handle_resume(instance.id, session)
    # /status and /snapshot are GET/POST on the API; not routable via turn
    await session.flush()

    return DirectiveResult(
        directive_raw=directive.raw_text,
        target_entity=target_slug,
        cmd=directive.cmd,
        results=[],
    )


async def _route_learning_directive(
    session: AsyncSession,
    workspace_id: str,
    directive: Directive,
    target_slug: str | None,
    from_user_id: str,
) -> DirectiveResult:
    """Route a learning command to the v4.9.3 distill flow.

    Bare cmds (target_slug is None) are silently dropped — matching the P5
    bare-cmd semantics. With an explicit @target, we look up the target
    Entity and distill its memory entries into capability_market rows
    (``created_via="distill"``, org scope) — NOT into a new BaseClass
    (v4.9.3 distill semantics: memory → capability). Emits a
    LEARNING_DISTILLATION_COMPLETED event and reports the created
    capabilities + engine_used on the DirectiveResult.

    Returns a ``DirectiveResult`` with the cmd echoed and an empty results
    list (learning commands don't produce ``MessageDeliveryResult`` rows).
    """
    if target_slug is None:
        return DirectiveResult(
            directive_raw=directive.raw_text,
            target_entity=None,
            cmd=directive.cmd,
            results=[],
        )

    emp_result = await session.execute(
        select(Entity).where(
            Entity.slug == target_slug,
            Entity.deleted_at.is_(None),
        )
    )
    target_entity = emp_result.scalars().first()
    if target_entity is None:
        return DirectiveResult(
            directive_raw=directive.raw_text,
            target_entity=target_slug,
            cmd=directive.cmd,
            results=[],
        )

    candidates = await _distill_memory_candidates(session, target_entity.id)
    if not candidates:
        return DirectiveResult(
            directive_raw=directive.raw_text,
            target_entity=target_slug,
            cmd=directive.cmd,
            results=[],
        )

    from app.core.capabilities import upsert_capability
    from app.core.event_types import LEARNING_DISTILLATION_COMPLETED
    from app.core.events import emit
    from app.models.organization import Namespace

    ns = await session.get(Namespace, target_entity.namespace_id)
    org_id = ns.org_id if ns is not None else None
    scope = "org" if org_id else "system"

    created_capabilities: list[dict[str, Any]] = []
    for candidate in candidates:
        cap = await upsert_capability(
            session,
            name=candidate["name"],
            cap_type=candidate["type"],
            scope=scope,
            organization_id=org_id,
            created_via="distill",
            description=candidate["description"],
            required_knowledge=candidate["required_knowledge"],
            source_entity_slug=target_entity.slug,
        )
        created_capabilities.append({"name": cap.name, "type": cap.type})

    await emit(
        LEARNING_DISTILLATION_COMPLETED,
        actor_type="user",
        actor_id=from_user_id,
        resource_type="entity",
        resource_id=target_entity.id,
        payload={
            "entity_id": target_entity.id,
            "source_entity_slug": target_entity.slug,
            "capability_names": [cap["name"] for cap in created_capabilities],
            "capability_count": len(created_capabilities),
            "engine_used": "heuristic",
        },
        session=session,
    )

    return DirectiveResult(
        directive_raw=directive.raw_text,
        target_entity=target_slug,
        cmd=directive.cmd,
        results=[],
        created_capabilities=created_capabilities,
        engine_used="heuristic",
    )
