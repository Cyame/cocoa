"""Directive routing engine.

Routes parsed Turn directives to target employees via corridor-gated delivery.
Chains parse_turn → route_message per directive → trigger_on_mention on success.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.activation import handle_intern_invocation, trigger_on_mention
from app.core.message_router import MessageDeliveryResult, route_message
from app.core.slash_parser import parse_turn
from app.models.employee import Employee, EmployeeRank
from app.models.office import Membership


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
