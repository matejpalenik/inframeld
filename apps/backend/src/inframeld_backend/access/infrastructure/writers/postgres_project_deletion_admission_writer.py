from datetime import timedelta
from typing import override
from uuid import uuid4

from sqlalchemy import DateTime, String, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.project_deletion_admission_writer import (
    ProjectDeletionAdmissionWriter,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_deletion_obligation_id import (
    ProjectDeletionObligationId,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.errors.job_errors import JobQueueFullError
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.rows.application_job_queue_row import (
    ApplicationJobQueueRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.rows.project_deletion_obligation_row import (
    ProjectDeletionObligationRow,
)


class PostgresProjectDeletionAdmissionWriter(ProjectDeletionAdmissionWriter):
    """Persist complete deletion admission without owning the caller's transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        capacity: int = 8,
        retention_profile: DeletionStatusRetentionProfile | None = None,
    ) -> None:
        self._session = session
        self._capacity = capacity
        self._retention_profile = retention_profile

    @override
    async def admit(
        self,
        *,
        installation_id: InstallationId,
        scope: ProjectActionAuthorizationDTO,
        access: AccessContextDTO,
        command: DeleteProjectCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
        reservation: NewOperationReservationDTO,
        fingerprint: RequestFingerprint,
        obligation_id: ProjectDeletionObligationId,
        job_id: JobId,
    ) -> None:
        """Save the block, one revision, audit, immutable original and durable capacity together.

        Require the caller's active READ COMMITTED transaction and already-held
        Organization/Project coordination. Recheck exact scope, ACTIVE status
        and reviewed revision before conditional persistence. Bind the genuine
        obligation, queued shutdown job and nonexpiring physical-pending parent
        to these original identities and request meaning. This is not ordinary
        JobAdmissionService authority or a caller-supplied admission certificate.

        Capacity denial and all failures propagate for complete rollback.
        Never commit, reset the original deadline, swallow cancellation or
        dispatch work here. No shutdown checkpoint or erasure success is implied.
        """
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Deletion admission requires its active caller transaction.")
        if (
            await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            != "read committed"
        ):
            raise RuntimeError("Deletion admission requires READ COMMITTED isolation.")
        if not 1 <= self._capacity <= 8:
            raise ValueError("Ordinary job capacity must be between one and eight.")
        if scope.project_id != command.project_id:
            raise ConflictError("Deletion admission changed its checked scope.")
        queue = await self._session.scalar(
            select(ApplicationJobQueueRow)
            .where(ApplicationJobQueueRow.singleton_key == 1)
            .with_for_update()
        )
        if queue is None:
            raise RuntimeError("The ordinary job queue is not initialized.")
        current = await ActionAuthorizationService(
            PostgresProjectActionFactsReader(self._session)
        ).require_authorization(
            access=access,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=scope.project_id, action_id=ActionId("delete-project")
            ),
        )
        if current != scope:
            raise ConflictError("Deletion authority changed the checked Project scope.")
        original = await self._session.scalar(
            select(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.operation_id == reservation.operation_id.value)
            .execution_options(populate_existing=True)
        )
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if (
            original is None
            or installed != installation_id.value
            or (
                original.organization_id,
                original.project_id,
                original.principal_id,
                original.method,
                original.requested_route,
                original.request_key,
                original.request_fingerprint,
                original.lookup_authority_family,
                original.lookup_action_id,
                original.state,
            )
            != (
                scope.organization_id.value,
                scope.project_id.value,
                access.actor_principal_id.value,
                "DELETE",
                f"/v1/projects/{scope.project_id.value}",
                context.key.value,
                fingerprint.value,
                "project_action_use",
                "delete-project",
                OperationReservationState.IN_PROGRESS,
            )
        ):
            raise ConflictError("Deletion admission has no matching original reservation.")
        if not await PostgresJobStore(self._session).has_fresh_capacity(capacity=self._capacity):
            raise JobQueueFullError("The ordinary job queue is full.")
        advanced = await self._session.scalar(
            update(ProjectRow)
            .where(
                ProjectRow.id == scope.project_id.value,
                ProjectRow.organization_id == scope.organization_id.value,
                ProjectRow.status == ProjectStatus.ACTIVE,
                ProjectRow.access_revision == command.expected_access_revision,
            )
            .values(
                status=ProjectStatus.DELETING, access_revision=command.expected_access_revision + 1
            )
            .returning(ProjectRow.id)
        )
        if advanced is None:
            raise StaleRevisionError()
        profile = (
            self._retention_profile
            if self._retention_profile is not None
            else DeletionStatusRetentionProfile()
        )
        self._session.add(
            DeletionStatusBindingRow(
                operation_id=reservation.operation_id.value,
                request_id=request_id.value,
                installation_id=installation_id.value,
                organization_id=scope.organization_id.value,
                project_id=scope.project_id.value,
                initiator_principal_id=access.actor_principal_id.value,
                method="DELETE",
                requested_route=context.requested_route,
                request_key=context.key.value,
                request_fingerprint=fingerprint.value,
                authority_family="project_action_use",
                action_id="delete-project",
                retention_days=profile.days,
                retention_policy_version=profile.policy_version,
            )
        )
        await self._session.flush()
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if now is None:
            raise RuntimeError("The database clock is unavailable.")
        self._session.add(
            ProjectDeletionObligationRow(
                id=obligation_id.value,
                job_id=job_id.value,
                operation_id=reservation.operation_id.value,
                request_id=request_id.value,
                installation_id=installation_id.value,
                organization_id=scope.organization_id.value,
                project_id=scope.project_id.value,
                initiator_principal_id=access.actor_principal_id.value,
                request_key=context.key.value,
                request_fingerprint=fingerprint.value,
                before_access_revision=command.expected_access_revision,
                access_revision=command.expected_access_revision + 1,
                admitted_at=now,
            )
        )
        await self._session.flush()
        self._session.add(
            DurableJobRow(
                id=job_id.value,
                operation_id=None,
                request_id=request_id.value,
                installation_id=installation_id.value,
                principal_id=None,
                principal_kind=None,
                organization_id=scope.organization_id.value,
                project_id=scope.project_id.value,
                action_id=None,
                payload_kind="project.application-shutdown",
                payload_version=1,
                payload=obligation_id.value.bytes,
                admitted_at=now,
                queued_deadline=now + timedelta(hours=24),
                due_at=now,
                binding_kind="project_deletion",
                deletion_obligation_id=obligation_id.value,
            )
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=scope.organization_id.value,
                project_id=scope.project_id.value,
                actor_kind="human",
                actor_principal_id=access.actor_principal_id.value,
                event_type="project_deletion_admitted",
                target_kind="project",
                target_id=scope.project_id.value,
                before_values={
                    "status": "active",
                    "access_revision": command.expected_access_revision,
                },
                after_values={
                    "status": "deleting",
                    "access_revision": command.expected_access_revision + 1,
                },
                correlation_id=reservation.operation_id.value,
            )
        )
        await self._session.flush()
