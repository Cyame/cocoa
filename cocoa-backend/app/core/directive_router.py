"""Directive routing engine.

Routes parsed Turn directives to target employees via corridor-gated delivery.
Chains parse_turn → route_message per directive → trigger_on_mention on success.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.activation import handle_intern_invocation, trigger_on_mention
from app.core.message_router import MessageDeliveryResult, route_message
from app.core.preset_registry import is_control_command, is_learning_command
from app.core.slash_parser import parse_turn
from app.models.employee import Employee, EmployeePreset, EmployeeRank
from app.models.office import Membership
from app.schemas.slash import Directive


@dataclass
class DirectiveResult:
    directive_raw: str
    target_employee: str | None
    cmd: str | None
    results: list[MessageDeliveryResult] = field(default_factory=list)


async def route_turn(
    session: AsyncSession,
    raw_text: str,
    office_id: str,
    from_user_id: str,
) -> list[DirectiveResult]:
    """Parse a turn and route each directive to its target employee.

    1. Parse raw_text into a Turn via P4's parse_turn
    2. Find the sender's Membership in this office
    3. For each directive:
       a. If target is an intern, ensure instance exists
       b. Route via message_router
       c. On successful delivery, trigger on_mention activation
    4. Return per-directive results
    """
    turn = parse_turn(raw_text)

    # Find the sender's membership
    result = await session.execute(
        select(Membership).where(
            Membership.user_id == from_user_id,
            Membership.office_id == office_id,
            Membership.deleted_at.is_(None),
        )
    )
    sender_membership = result.scalars().first()
    if sender_membership is None:
        return []  # Sender not a member of this office

    directive_results: list[DirectiveResult] = []

    for directive in turn.directives:
        target_slug = directive.target_employee

        # CONTROL COMMAND BRANCH (P8) — routes to Harness Supervisor, NOT corridor
        # Bare cmds (target_slug is None) are silently dropped, matching P5 contract.
        if is_control_command(directive.cmd):
            directive_results.append(
                await _route_control_directive(
                    session=session,
                    office_id=office_id,
                    directive=directive,
                    target_slug=target_slug,
                )
            )
            continue

        # LEARNING COMMAND BRANCH (P10) — routes to AggregatingDistiller,
        # NOT corridor. Requires explicit @target; bare cmds are silently
        # dropped, matching P5 bare-cmd semantics.
        if is_learning_command(directive.cmd):
            directive_results.append(
                await _route_learning_directive(
                    session=session,
                    office_id=office_id,
                    directive=directive,
                    target_slug=target_slug,
                    from_user_id=from_user_id,
                )
            )
            continue

        # If target is an intern, ensure instance exists (hot-load)
        if target_slug:
            # Check if target is intern
            result = await session.execute(
                select(Employee).where(
                    Employee.slug == target_slug,
                    Employee.deleted_at.is_(None),
                )
            )
            target_employee = result.scalars().first()
            if target_employee and target_employee.rank == EmployeeRank.intern:
                await handle_intern_invocation(session, target_slug, office_id)

        # Route the directive
        delivery_results = await route_message(
            session=session,
            from_membership_id=sender_membership.id,
            office_id=office_id,
            directive=directive,
        )

        # Trigger on_mention for successful deliveries
        for result_obj in delivery_results:
            if result_obj.delivered and target_employee:
                await trigger_on_mention(
                    session=session,
                    employee_id=target_employee.id,
                    office_id=office_id,
                )

        directive_results.append(
            DirectiveResult(
                directive_raw=directive.raw_text,
                target_employee=target_slug,
                cmd=directive.cmd,
                results=delivery_results,
            )
        )

    return directive_results


async def _route_control_directive(
    session: AsyncSession,
    office_id: str,
    directive: Directive,
    target_slug: str | None,
) -> DirectiveResult:
    """Route a control command to the Harness Supervisor.

    Bare cmds (target_slug is None) are silently dropped — matching the P5
    bare-cmd semantics in ``app/core/message_router.py:93-94``. With an
    explicit @target, we look up the target Employee's active Instance in
    this office and dispatch to the corresponding Supervisor action.

    Returns a ``DirectiveResult`` with the cmd echoed and an empty results
    list (control commands don't produce ``MessageDeliveryResult`` rows;
    their effect is on the harness state, not the message log).
    """
    if target_slug is None:
        # Bare cmd — silently drop per P5 bare-cmd semantics
        return DirectiveResult(
            directive_raw=directive.raw_text,
            target_employee=None,
            cmd=directive.cmd,
            results=[],
        )

    emp_result = await session.execute(
        select(Employee).where(
            Employee.slug == target_slug,
            Employee.deleted_at.is_(None),
        )
    )
    target_employee = emp_result.scalars().first()
    if target_employee is None:
        return DirectiveResult(
            directive_raw=directive.raw_text,
            target_employee=target_slug,
            cmd=directive.cmd,
            results=[],
        )

    from app.models.instance import Instance, InstanceStatus

    inst_result = await session.execute(
        select(Instance).where(
            Instance.employee_id == target_employee.id,
            Instance.office_id == office_id,
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
            target_employee=target_slug,
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
        target_employee=target_slug,
        cmd=directive.cmd,
        results=[],
    )


async def _route_learning_directive(
    session: AsyncSession,
    office_id: str,
    directive: Directive,
    target_slug: str | None,
    from_user_id: str,
) -> DirectiveResult:
    """Route a learning command to the AggregatingDistiller.

    Bare cmds (target_slug is None) are silently dropped — matching the P5
    bare-cmd semantics. With an explicit @target, we look up the target
    Employee, run distillation on their memory entries, create a new
    EmployeePreset, and emit a LEARNING_DISTILLATION_COMPLETED event.

    Returns a ``DirectiveResult`` with the cmd echoed and an empty results
    list (learning commands don't produce ``MessageDeliveryResult`` rows).
    """
    if target_slug is None:
        return DirectiveResult(
            directive_raw=directive.raw_text,
            target_employee=None,
            cmd=directive.cmd,
            results=[],
        )

    emp_result = await session.execute(
        select(Employee).where(
            Employee.slug == target_slug,
            Employee.deleted_at.is_(None),
        )
    )
    target_employee = emp_result.scalars().first()
    if target_employee is None:
        return DirectiveResult(
            directive_raw=directive.raw_text,
            target_employee=target_slug,
            cmd=directive.cmd,
            results=[],
        )

    from app.core.distillation import AggregatingDistiller
    from app.core.event_types import LEARNING_DISTILLATION_COMPLETED
    from app.core.events import emit
    from app.schemas.learning import DistillRequest

    target_skill_slug = (
        directive.args[0] if directive.args else "default-skill"
    )
    request = DistillRequest(
        target_skill_slug=target_skill_slug,
        memory_kind_filter=None,
        source_preset_slug=target_employee.preset_slug,
        target_preset_name=None,
    )
    result = await AggregatingDistiller().distill(
        target_employee.id, request=request, session=session,
    )

    new_preset = EmployeePreset(
        slug=result.new_preset_slug,
        name=f"Skill: {target_skill_slug}",
        manifest=result.manifest_preview.model_dump(),
    )
    session.add(new_preset)
    await session.flush()

    await emit(
        event_type=LEARNING_DISTILLATION_COMPLETED,
        actor_type="user",
        actor_id=from_user_id,
        resource_type="employee_preset",
        resource_id=new_preset.id,
        payload={
            "employee_id": target_employee.id,
            "new_preset_slug": result.new_preset_slug,
            "source_preset_slug": target_employee.preset_slug,
            "aggregated_counts": result.aggregated_memory.model_dump(),
        },
        session=session,
    )

    return DirectiveResult(
        directive_raw=directive.raw_text,
        target_employee=target_slug,
        cmd=directive.cmd,
        results=[],
    )
