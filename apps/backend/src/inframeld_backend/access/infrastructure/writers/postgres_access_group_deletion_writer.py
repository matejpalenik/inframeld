from datetime import datetime, timedelta
from typing import override
from uuid import uuid4

from sqlalchemy import DateTime, delete, func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.deleted_access_group_dto import DeletedAccessGroupDTO
from inframeld_backend.access.application.protocols.access_group_deletion_writer import (
    AccessGroupDeletionWriter,
)
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_deletion_result_row import (
    AccessGroupDeletionResultRow,
)
from inframeld_backend.access.infrastructure.rows.access_group_name_reservation_row import (
    AccessGroupNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresAccessGroupDeletionWriter(AccessGroupDeletionWriter):
    """Publish synchronous completion only alongside an actual scoped group deletion."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def delete(
        self,
        *,
        group: DeletedAccessGroupDTO,
        expected_project_revision: int,
        binding: DeletionStatusBindingDTO,
    ) -> None:
        try:
            await self._delete(group, expected_project_revision, binding)
        except IntegrityError:
            raise ConflictError("A stored reference prevents deleting this access group.") from None
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _delete(
        self,
        group: DeletedAccessGroupDTO,
        expected_project_revision: int,
        binding: DeletionStatusBindingDTO,
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Group deletion requires an active caller transaction.")
        RevisionValidation.require(expected_project_revision)
        RevisionValidation.require(group.access_revision)
        route = f"/v1/projects/{group.project_id.value}/access-groups/{group.group_id.value}"
        if (
            group.access_revision != expected_project_revision + 1
            or binding.operation_id != group.operation_id
            or binding.organization_id != group.organization_id
            or binding.project_id != group.project_id
            or binding.initiator_principal_id != group.actor_principal_id
            or binding.method != "DELETE"
            or binding.requested_route != route
            or binding.authority_family is not OperationLookupAuthorityFamily.ACCESS_GROUP_DELETION
            or binding.action_id is None
            or binding.action_id.value != "delete-access-group"
            or binding.retention_days is None
            or binding.retention_policy_version is None
        ):
            raise ConflictError("Group completion changed its original deletion binding.")
        profile = DeletionStatusRetentionProfile(
            binding.retention_days, binding.retention_policy_version
        )
        native, retained = IdempotencyReservationRow, DeletionStatusBindingRow
        original = await self._session.scalar(
            select(native.operation_id)
            .join(retained, retained.operation_id == native.operation_id)
            .where(
                native.operation_id == group.operation_id.value,
                native.organization_id == group.organization_id.value,
                native.project_id == group.project_id.value,
                native.principal_id == group.actor_principal_id.value,
                native.method == "DELETE",
                native.requested_route == route,
                native.request_key == binding.key.value,
                native.request_fingerprint == binding.fingerprint.value,
                native.lookup_authority_family == "access_group_deletion",
                native.lookup_action_id == "delete-access-group",
                native.state == OperationReservationState.IN_PROGRESS,
                native.replay_kind.is_(None),
                native.expires_at.is_(None),
                retained.request_id == binding.request_id.value,
                retained.installation_id == binding.installation_id.value,
                retained.organization_id == native.organization_id,
                retained.project_id == native.project_id,
                retained.initiator_principal_id == native.principal_id,
                retained.method == native.method,
                retained.requested_route == native.requested_route,
                retained.request_key == native.request_key,
                retained.request_fingerprint == native.request_fingerprint,
                retained.authority_family == native.lookup_authority_family,
                retained.action_id == native.lookup_action_id,
                retained.retention_days == profile.days,
                retained.retention_policy_version == profile.policy_version,
                retained.recorded_at == binding.recorded_at,
            )
        )
        if original is None:
            raise ConflictError("Group completion has no authentic original deletion binding.")
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
        # These are the actual owned relationships. Future content/default owners
        # must add restrictive scoped references and compatible coordination.
        for relation in (GroupManagerRow, GroupMembershipRow, GroupActionGrantRow):
            await self._session.execute(
                delete(relation).where(
                    relation.project_id == group.project_id.value,
                    relation.group_id == group.group_id.value,
                )
            )
        removed = await self._session.scalar(
            delete(AccessGroupRow)
            .where(
                AccessGroupRow.id == group.group_id.value,
                AccessGroupRow.project_id == group.project_id.value,
            )
            .returning(AccessGroupRow.id)
        )
        if removed != group.group_id.value:
            raise ConflictError("The checked group disappeared before deletion.")
        await self._session.execute(
            update(AccessGroupNameReservationRow)
            .where(
                AccessGroupNameReservationRow.project_id == group.project_id.value,
                AccessGroupNameReservationRow.group_id == group.group_id.value,
            )
            .values(retired=True)
        )
        self._session.add(
            AccessGroupDeletionResultRow(
                operation_id=group.operation_id.value,
                organization_id=group.organization_id.value,
                project_id=group.project_id.value,
                group_id=group.group_id.value,
                actor_principal_id=group.actor_principal_id.value,
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
                actor_principal_id=group.actor_principal_id.value,
                event_type="access_group_deleted",
                target_kind="access_group",
                target_id=group.group_id.value,
                before_values={"access_revision": expected_project_revision},
                after_values={"removed": True, "access_revision": group.access_revision},
                correlation_id=group.operation_id.value,
            )
        )
        started = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if not isinstance(started, datetime) or started < binding.recorded_at:
            raise DependencyUnavailableError()
        self._session.add(
            DeletionStatusObservationRow(
                operation_id=group.operation_id.value,
                owner_revision=group.access_revision,
                admission_confirmed=True,
                access_blocked=True,
                physical_cleanup_complete=True,
                retention_started_at=started,
                expires_at=started + timedelta(days=profile.days),
            )
        )
        await self._session.flush()
