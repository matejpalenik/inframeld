from typing import override
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.protocols.access_group_relationship_writer import (
    AccessGroupRelationshipWriter,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_relationship_result_row import (
    AccessGroupRelationshipResultRow,
)
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
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
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresAccessGroupRelationshipWriter(AccessGroupRelationshipWriter):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def save(
        self,
        *,
        facts: AccessGroupChangeFactsDTO,
        command: ChangeAccessGroupRelationshipCommand,
        operation_id: OperationId,
        after: AccessGroupRelationships,
    ) -> None:
        try:
            await self._save(facts, command, operation_id, after)
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _save(
        self,
        facts: AccessGroupChangeFactsDTO,
        command: ChangeAccessGroupRelationshipCommand,
        operation_id: OperationId,
        after: AccessGroupRelationships,
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Group persistence requires an active caller transaction.")
        actor, recipient, kind = facts.action.principal, facts.recipient, command.change_kind
        if (
            facts.group_id != command.group_id
            or facts.project_id != command.project_id
            or recipient is None
            or recipient.id != command.principal_id
            or recipient.organization_id != facts.organization_id
            or actor.organization_id != facts.organization_id
            or actor.kind is not PrincipalKind.HUMAN
        ):
            raise RuntimeError("Group persistence changed its checked actor or recipient scope.")
        if after.manager and recipient.kind is not PrincipalKind.HUMAN:
            raise ConflictError("Application principals cannot manage access groups.")
        project, group, principal = (
            command.project_id.value,
            command.group_id.value,
            command.principal_id.value,
        )
        native = IdempotencyReservationRow
        route = f"/v1/projects/{project}/access-groups/{group}/{kind.collection}/{principal}"
        if (
            await self._session.scalar(
                select(native.operation_id).where(
                    native.operation_id == operation_id.value,
                    native.organization_id == facts.organization_id.value,
                    native.project_id == project,
                    native.principal_id == actor.id.value,
                    native.method == kind.http_method,
                    native.requested_route == route,
                    native.lookup_authority_family.is_(None),
                    native.lookup_action_id.is_(None),
                    native.state == OperationReservationState.IN_PROGRESS,
                    native.replay_kind.is_(None),
                    native.expires_at.is_(None),
                )
            )
            is None
        ):
            raise ConflictError("The group transition has no matching original reservation.")
        revision = await self._session.scalar(
            select(ProjectRow.access_revision).where(
                ProjectRow.id == project,
                ProjectRow.organization_id == facts.organization_id.value,
                ProjectRow.status == ProjectStatus.ACTIVE,
            )
        )
        if (
            revision is None
            or revision != facts.access_revision
            or revision != command.expected_access_revision
        ):
            raise StaleRevisionError()
        member = await self._session.get(
            GroupMembershipRow, (project, group, principal), populate_existing=True
        )
        manager = await self._session.get(
            GroupManagerRow, (project, group, principal), populate_existing=True
        )
        before = AccessGroupRelationships(member=member is not None, manager=manager is not None)
        if before != facts.relationships:
            raise ConflictError("The checked group relationships changed before persistence.")
        changed = before != after
        if before.manager and not after.manager:
            await self._session.execute(
                delete(GroupManagerRow).where(
                    GroupManagerRow.project_id == project,
                    GroupManagerRow.group_id == group,
                    GroupManagerRow.principal_id == principal,
                )
            )
        if before.member and not after.member:
            await self._session.execute(
                delete(GroupMembershipRow).where(
                    GroupMembershipRow.project_id == project,
                    GroupMembershipRow.group_id == group,
                    GroupMembershipRow.principal_id == principal,
                )
            )
        if not before.member and after.member:
            self._session.add(
                GroupMembershipRow(
                    project_id=project,
                    group_id=group,
                    principal_id=principal,
                    assigned_by_principal_id=actor.id.value,
                )
            )
            await self._session.flush()
        if not before.manager and after.manager:
            self._session.add(
                GroupManagerRow(
                    project_id=project,
                    group_id=group,
                    principal_id=principal,
                    principal_kind=PrincipalKind.HUMAN,
                    assigned_by_principal_id=actor.id.value,
                )
            )
        if changed:
            if revision == RevisionValidation.MAX_VALUE:
                raise ConflictError("The Project Access revision cannot advance.")
            advanced = await self._session.scalar(
                update(ProjectRow)
                .where(
                    ProjectRow.id == project,
                    ProjectRow.organization_id == facts.organization_id.value,
                    ProjectRow.access_revision == revision,
                    ProjectRow.status == ProjectStatus.ACTIVE,
                )
                .values(access_revision=revision + 1)
                .returning(ProjectRow.access_revision)
            )
            if advanced != revision + 1:
                raise StaleRevisionError()
        self._session.add(
            AccessGroupRelationshipResultRow(
                operation_id=operation_id.value,
                organization_id=facts.organization_id.value,
                project_id=project,
                group_id=group,
                actor_principal_id=actor.id.value,
                principal_id=principal,
                change_kind=kind.value,
                before_revision=revision,
                access_revision=revision + int(changed),
                before_member=before.member,
                before_manager=before.manager,
                member=after.member,
                manager=after.manager,
                changed=changed,
                status_code=kind.success_status(changed=changed),
            )
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=facts.organization_id.value,
                project_id=project,
                actor_kind="human",
                actor_principal_id=actor.id.value,
                affected_principal_id=principal,
                event_type="access_group_relationship_changed"
                if changed
                else "access_group_relationship_unchanged",
                target_kind="access_group",
                target_id=group,
                before_values={
                    "member": before.member,
                    "manager": before.manager,
                    "access_revision": revision,
                },
                after_values={
                    "change": kind.value,
                    "member": after.member,
                    "manager": after.manager,
                    "access_revision": revision + int(changed),
                },
                correlation_id=operation_id.value,
            )
        )
        await self._session.flush()
