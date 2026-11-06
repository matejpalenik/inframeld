from typing import override
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.created_access_group_dto import CreatedAccessGroupDTO
from inframeld_backend.access.application.protocols.access_group_creation_writer import (
    AccessGroupCreationWriter,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_creation_result_row import (
    AccessGroupCreationResultRow,
)
from inframeld_backend.access.infrastructure.rows.access_group_name_reservation_row import (
    AccessGroupNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
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
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresAccessGroupCreationWriter(AccessGroupCreationWriter):
    """Save the named group and creator relationships in the checked write transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def create(self, *, group: CreatedAccessGroupDTO, expected_project_revision: int) -> None:
        try:
            if not self._session.in_transaction() or not self._session.is_active:
                raise RuntimeError("Group creation requires an active caller transaction.")
            RevisionValidation.require(expected_project_revision)
            RevisionValidation.require(group.access_revision)
            if group.access_revision != expected_project_revision + 1:
                raise RuntimeError("Group creation changed the checked revision.")
            native = IdempotencyReservationRow
            if (
                await self._session.scalar(
                    select(native.operation_id).where(
                        native.operation_id == group.operation_id.value,
                        native.organization_id == group.organization_id.value,
                        native.project_id == group.project_id.value,
                        native.principal_id == group.creator_principal_id.value,
                        native.method == "POST",
                        native.requested_route
                        == f"/v1/projects/{group.project_id.value}/access-groups",
                        native.lookup_authority_family == "project_action_use",
                        native.lookup_action_id == "create-access-groups",
                        native.state == OperationReservationState.IN_PROGRESS,
                    )
                )
                is None
            ):
                raise ConflictError("Group creation has no matching original reservation.")
            human = await self._session.scalar(
                select(PrincipalRow.id)
                .join(ProjectMembershipRow, ProjectMembershipRow.principal_id == PrincipalRow.id)
                .where(
                    PrincipalRow.id == group.creator_principal_id.value,
                    PrincipalRow.organization_id == group.organization_id.value,
                    PrincipalRow.kind == PrincipalKind.HUMAN,
                    PrincipalRow.status == PrincipalStatus.ACTIVE,
                    ProjectMembershipRow.project_id == group.project_id.value,
                    ProjectMembershipRow.organization_id == group.organization_id.value,
                )
            )
            if human is None:
                raise ConflictError("The checked group creator is no longer eligible.")
            if (
                await self._session.scalar(
                    update(ProjectRow)
                    .where(
                        ProjectRow.id == group.project_id.value,
                        ProjectRow.organization_id == group.organization_id.value,
                        ProjectRow.status == ProjectStatus.ACTIVE,
                        ProjectRow.access_revision == expected_project_revision,
                        ProjectRow.access_revision < RevisionValidation.MAX_VALUE,
                    )
                    .values(access_revision=group.access_revision)
                    .returning(ProjectRow.id)
                )
                is None
            ):
                raise StaleRevisionError()
            allocated = await self._session.scalar(
                insert(AccessGroupNameReservationRow)
                .values(
                    project_id=group.project_id.value,
                    name=group.name.value,
                    organization_id=group.organization_id.value,
                    group_id=group.group_id.value,
                    retired=False,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        AccessGroupNameReservationRow.project_id,
                        AccessGroupNameReservationRow.name,
                    ]
                )
                .returning(AccessGroupNameReservationRow.name)
            )
            if allocated is None:
                raise ConflictError("The requested access-group Name is unavailable.")
            self._session.add(
                AccessGroupRow(
                    id=group.group_id.value,
                    project_id=group.project_id.value,
                    name=group.display_name,
                    resource_name=group.name.value,
                )
            )
            await self._session.flush()
            self._session.add(
                GroupMembershipRow(
                    project_id=group.project_id.value,
                    group_id=group.group_id.value,
                    principal_id=human,
                    assigned_by_principal_id=human,
                )
            )
            await self._session.flush()
            self._session.add(
                GroupManagerRow(
                    project_id=group.project_id.value,
                    group_id=group.group_id.value,
                    principal_id=human,
                    principal_kind=PrincipalKind.HUMAN,
                    assigned_by_principal_id=human,
                )
            )
            self._session.add(
                AccessGroupCreationResultRow(
                    operation_id=group.operation_id.value,
                    organization_id=group.organization_id.value,
                    project_id=group.project_id.value,
                    group_id=group.group_id.value,
                    actor_principal_id=human,
                    name=group.name.value,
                    display_name=group.display_name,
                    before_revision=expected_project_revision,
                    access_revision=group.access_revision,
                )
            )
            self._session.add(
                AccessAuditEventRow(
                    id=uuid4(),
                    organization_id=group.organization_id.value,
                    project_id=group.project_id.value,
                    actor_kind="human",
                    actor_principal_id=human,
                    event_type="access_group_created",
                    target_kind="access_group",
                    target_id=group.group_id.value,
                    after_values={
                        "name": group.name.value,
                        "display_name": group.display_name,
                        "creator_principal_id": str(human),
                        "member": True,
                        "manager": True,
                        "access_revision": group.access_revision,
                    },
                    correlation_id=group.operation_id.value,
                )
            )
            await self._session.flush()
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
