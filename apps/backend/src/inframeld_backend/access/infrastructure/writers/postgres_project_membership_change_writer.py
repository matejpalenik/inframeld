from typing import Literal, override
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.protocols.project_membership_change_writer import (
    ProjectMembershipChangeWriter,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_operation_result_row import (
    ProjectMembershipOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresProjectMembershipChangeWriter(ProjectMembershipChangeWriter):
    """Persist one checked recipient's lifecycle and original receipt atomically."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def save(
        self,
        *,
        facts: ProjectMembershipChangeFactsDTO,
        principal_id: PrincipalId,
        change_kind: Literal["add", "remove"],
        operation_id: OperationId,
    ) -> None:
        try:
            await self._save(facts, principal_id, change_kind, operation_id)
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _save(
        self,
        facts: ProjectMembershipChangeFactsDTO,
        principal_id: PrincipalId,
        change_kind: Literal["add", "remove"],
        operation_id: OperationId,
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Membership persistence requires the active caller transaction.")
        actor = facts.action.principal
        if (
            facts.recipient is None
            or facts.recipient.id != principal_id
            or facts.recipient.organization_id != facts.organization_id
            or facts.recipient.kind is not PrincipalKind.HUMAN
            or actor.organization_id != facts.organization_id
            or actor.kind is not PrincipalKind.HUMAN
        ):
            raise RuntimeError(
                "Membership persistence changed its checked recipient or actor scope."
            )
        project, organization, recipient = (
            facts.project_id.value,
            facts.organization_id.value,
            principal_id.value,
        )
        method = "PUT" if change_kind == "add" else "DELETE"
        route = f"/v1/projects/{project}/members/{recipient}"
        with self._session.no_autoflush:
            reservation = await self._session.scalar(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.operation_id == operation_id.value,
                    IdempotencyReservationRow.principal_id == actor.id.value,
                    IdempotencyReservationRow.organization_id == organization,
                    IdempotencyReservationRow.project_id == project,
                    IdempotencyReservationRow.method == method,
                    IdempotencyReservationRow.requested_route == route,
                    IdempotencyReservationRow.lookup_authority_family == "project_action_use",
                    IdempotencyReservationRow.lookup_action_id == "manage-project-members",
                    IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
                    IdempotencyReservationRow.replay_kind.is_(None),
                    IdempotencyReservationRow.expires_at.is_(None),
                )
            )
            if reservation is None:
                raise ConflictError("Membership change has no matching original reservation.")
            revision = await self._session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == project,
                    ProjectRow.organization_id == organization,
                    ProjectRow.status == ProjectStatus.ACTIVE,
                )
            )
            if revision is None or revision != facts.access_revision:
                raise StaleRevisionError()
            member = await self._session.scalar(
                select(ProjectMembershipRow)
                .where(
                    ProjectMembershipRow.project_id == project,
                    ProjectMembershipRow.organization_id == organization,
                    ProjectMembershipRow.principal_id == recipient,
                )
                .execution_options(populate_existing=True)
            )
            if (member is not None) != facts.recipient_is_project_member or (
                member is not None and member.principal_kind is not PrincipalKind.HUMAN
            ):
                raise ConflictError("The checked membership changed before persistence.")

        changed = (
            not facts.recipient_is_project_member
            if change_kind == "add"
            else facts.recipient_is_project_member
        )
        if changed and change_kind == "add":
            self._session.add(
                ProjectMembershipRow(
                    project_id=project,
                    organization_id=organization,
                    principal_id=recipient,
                    principal_kind=PrincipalKind.HUMAN,
                    assigned_by_principal_id=actor.id.value,
                )
            )
            await self._session.flush()
        elif changed:
            await self._session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == project,
                    ProjectActionGrantRow.recipient_principal_id == recipient,
                )
            )
            await self._session.execute(
                delete(GroupActionGrantRow).where(
                    GroupActionGrantRow.project_id == project,
                    GroupActionGrantRow.recipient_principal_id == recipient,
                )
            )
            await self._session.execute(
                delete(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.project_id == project,
                    ApplicationActionGrantRow.recipient_principal_id == recipient,
                )
            )
            # The manager-membership foreign key requires this dependency order.
            await self._session.execute(
                delete(GroupManagerRow).where(
                    GroupManagerRow.project_id == project, GroupManagerRow.principal_id == recipient
                )
            )
            await self._session.execute(
                delete(GroupMembershipRow).where(
                    GroupMembershipRow.project_id == project,
                    GroupMembershipRow.principal_id == recipient,
                )
            )
            removed = await self._session.scalar(
                delete(ProjectMembershipRow)
                .where(
                    ProjectMembershipRow.project_id == project,
                    ProjectMembershipRow.organization_id == organization,
                    ProjectMembershipRow.principal_id == recipient,
                )
                .returning(ProjectMembershipRow.principal_id)
            )
            if removed != recipient:
                raise ConflictError("The checked membership disappeared before persistence.")
        if changed:
            advanced = await self._session.scalar(
                update(ProjectRow)
                .where(
                    ProjectRow.id == project,
                    ProjectRow.organization_id == organization,
                    ProjectRow.access_revision == revision,
                    ProjectRow.status == ProjectStatus.ACTIVE,
                )
                .values(access_revision=ProjectRow.access_revision + 1)
                .returning(ProjectRow.access_revision)
            )
            if advanced != revision + 1:
                raise StaleRevisionError()

        after = revision + int(changed)
        self._session.add(
            ProjectMembershipOperationResultRow(
                operation_id=operation_id.value,
                installation_id=facts.installation_id.value,
                organization_id=organization,
                project_id=project,
                actor_principal_id=actor.id.value,
                principal_id=recipient,
                change_kind=change_kind,
                before_revision=revision,
                access_revision=after,
                changed=changed,
                status_code=201 if change_kind == "add" and changed else 200,
            )
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=organization,
                project_id=project,
                actor_kind=PrincipalKind.HUMAN.value,
                actor_principal_id=actor.id.value,
                affected_principal_id=recipient,
                event_type=(
                    "project_member_added" if change_kind == "add" else "project_member_removed"
                )
                if changed
                else "project_membership_unchanged",
                target_kind="project",
                target_id=project,
                action="manage-project-members",
                before_values={
                    "access_revision": revision,
                    "member": facts.recipient_is_project_member,
                },
                after_values={"access_revision": after, "member": change_kind == "add"},
                correlation_id=operation_id.value,
            )
        )
        await self._session.flush()
