"""Message delivery router — fire-and-forget delivery with corridor gating.

Routes a parsed directive to eligible recipient employees within an office.
Delivery only succeeds when an active Corridor edge exists from the sender's
membership to the target instance's membership (corridor gating).

Fire-and-forget: message content is NOT persisted to the database.  Only
audit events (messaging.message_sent / messaging.delivery_blocked) are
emitted for observability.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_types import MESSAGING_DELIVERY_BLOCKED, MESSAGING_MESSAGE_SENT
from app.core.events import emit
from app.models.employee import Employee
from app.models.instance import Instance, InstanceStatus
from app.models.office import Corridor, Membership
from app.schemas.slash import Directive

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class MessageDeliveryResult:
    """Outcome of attempting to deliver a message to one target instance.

    Attributes:
        target_employee: Employee slug the directive was addressed to.
        delivered: Whether the message passed corridor gating.
        reason: Machine-readable failure code when ``delivered`` is False.
            Possible values: ``"employee_not_found"``,
            ``"no_active_instance"``, ``"not_neighbor"``.
        instance_id: UUID of the target :class:`~app.models.instance.Instance`
            (populated for gating-attempt results, ``None`` for early-out
            rejections like ``employee_not_found``).
    """

    target_employee: str
    delivered: bool
    reason: str | None = None
    instance_id: str | None = None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


async def route_message(
    session: AsyncSession,
    from_membership_id: str,
    office_id: str,
    directive: Directive,
    general_text: str | None = None,
) -> list[MessageDeliveryResult]:
    """Attempt to deliver *directive* to eligible recipients in an office.

    Delivery is gated by the corridor graph: a message is only delivered
    to a target instance when an active :class:`~app.models.office.Corridor`
    edge exists from *from_membership_id* to the target instance's membership.

    Parameters
    ----------
    session:
        Active async database session.  The caller owns the transaction
        boundary — this function never commits.
    from_membership_id:
        UUID of the sender's :class:`~app.models.office.Membership`.
    office_id:
        UUID of the office where delivery occurs.
    directive:
        Parsed directive.  ``target_employee`` identifies the recipient;
        a bare ``/cmd`` with ``target_employee=None`` is silently skipped.
    general_text:
        Optional free-form text accompanying the directive.  Included in
        success audit payloads but never persisted as message content.

    Returns
    -------
    list[MessageDeliveryResult]
        One result per target instance that was attempted.  Empty list when
        ``directive.target_employee`` is ``None``.
    """
    # ---- bare /cmd (no target) -----------------------------------------
    if directive.target_employee is None:
        return []

    # ---- resolve target employee ---------------------------------------
    result = await session.execute(
        select(Employee).where(
            Employee.slug == directive.target_employee,
            Employee.deleted_at.is_(None),
        )
    )
    employee = result.scalar_one_or_none()
    if employee is None:
        return [
            MessageDeliveryResult(
                target_employee=directive.target_employee,
                delivered=False,
                reason="employee_not_found",
            )
        ]

    # ---- resolve active instances in this office -----------------------
    result = await session.execute(
        select(Instance).where(
            Instance.employee_id == employee.id,
            Instance.office_id == office_id,
            Instance.status.in_([InstanceStatus.running, InstanceStatus.pending]),
            Instance.deleted_at.is_(None),
        )
    )
    instances = result.scalars().all()
    if not instances:
        return [
            MessageDeliveryResult(
                target_employee=directive.target_employee,
                delivered=False,
                reason="no_active_instance",
            )
        ]

    # ---- per-instance corridor gate ------------------------------------
    results: list[MessageDeliveryResult] = []

    for instance in instances:
        # --- resolve target membership ---
        result = await session.execute(
            select(Membership).where(
                Membership.instance_id == instance.id,
                Membership.office_id == office_id,
                Membership.deleted_at.is_(None),
            )
        )
        to_membership = result.scalar_one_or_none()
        if to_membership is None:
            # Instance exists but has no membership — treat as not neighbor
            await emit(
                MESSAGING_DELIVERY_BLOCKED,
                actor_type="membership",
                actor_id=from_membership_id,
                resource_type="instance",
                resource_id=instance.id,
                payload={
                    "target_employee": directive.target_employee,
                    "cmd": directive.cmd,
                    "office_id": office_id,
                    "instance_id": instance.id,
                    "reason_detail": "target_membership_missing",
                },
                session=session,
            )
            results.append(
                MessageDeliveryResult(
                    target_employee=directive.target_employee,
                    delivered=False,
                    reason="not_neighbor",
                    instance_id=instance.id,
                )
            )
            continue

        # --- check corridor edge ---
        result = await session.execute(
            select(Corridor).where(
                Corridor.office_id == office_id,
                Corridor.from_membership_id == from_membership_id,
                Corridor.to_membership_id == to_membership.id,
                Corridor.is_active,
                Corridor.deleted_at.is_(None),
            )
        )
        corridor = result.scalar_one_or_none()

        if corridor is None:
            # No active corridor → delivery blocked
            await emit(
                MESSAGING_DELIVERY_BLOCKED,
                actor_type="membership",
                actor_id=from_membership_id,
                resource_type="membership",
                resource_id=to_membership.id,
                payload={
                    "target_employee": directive.target_employee,
                    "cmd": directive.cmd,
                    "office_id": office_id,
                    "instance_id": instance.id,
                    "to_membership_id": to_membership.id,
                },
                session=session,
            )
            results.append(
                MessageDeliveryResult(
                    target_employee=directive.target_employee,
                    delivered=False,
                    reason="not_neighbor",
                    instance_id=instance.id,
                )
            )
        else:
            # Active corridor present → deliver
            await emit(
                MESSAGING_MESSAGE_SENT,
                actor_type="membership",
                actor_id=from_membership_id,
                resource_type="instance",
                resource_id=instance.id,
                payload={
                    "target_employee": directive.target_employee,
                    "cmd": directive.cmd,
                    "args": directive.args,
                    "office_id": office_id,
                    "instance_id": instance.id,
                    "to_membership_id": to_membership.id,
                    "corridor_id": corridor.id,
                    "general_text": general_text,
                },
                session=session,
            )
            results.append(
                MessageDeliveryResult(
                    target_employee=directive.target_employee,
                    delivered=True,
                    instance_id=instance.id,
                )
            )

    return results
