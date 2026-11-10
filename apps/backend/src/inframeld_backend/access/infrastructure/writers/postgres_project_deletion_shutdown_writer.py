from typing import override
from uuid import uuid4

from sqlalchemy import String, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import SessionTransaction

from inframeld_backend.access.application.dtos.project_deletion_shutdown_facts_dto import (
    ProjectDeletionShutdownFactsDTO,
)
from inframeld_backend.access.application.protocols.project_deletion_shutdown_writer import (
    ProjectDeletionShutdownWriter,
)
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.errors.job_errors import JobFenceLostError
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.rows.project_deletion_obligation_row import (
    ProjectDeletionObligationRow,
)


class PostgresProjectDeletionShutdownWriter(ProjectDeletionShutdownWriter):
    """Persist only the checked local shutdown checkpoint inside its caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._transaction: SessionTransaction | None = None
        self._facts: ProjectDeletionShutdownFactsDTO | None = None
        self._context: JobAttemptContextDTO | None = None

    @override
    async def lock_original(self, context: JobAttemptContextDTO) -> ProjectDeletionShutdownFactsDTO:
        """Lock Organization, Project and original obligation in that order.

        Require the caller's active READ COMMITTED transaction and original
        deadline. Refresh actual scope, DELETING lifecycle and parent facts
        after waits. These observations are not an admission or fence certificate.
        The caller then acquires exact job ownership before application effects.
        Missing or conflicting required backing fails closed, never provisions it.
        """
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Shutdown persistence requires its active caller transaction.")
        if (
            await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            != "read committed"
        ):
            raise RuntimeError("Shutdown persistence requires READ COMMITTED isolation.")
        binding = context.binding
        if not isinstance(binding, ProjectDeletionJobBindingDTO):
            raise ConflictError("Shutdown requires the original deletion binding.")
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed is None or installed != binding.installation_id.value:
            raise ConflictError("Shutdown changed the original installation.")
        if (
            await self._session.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == binding.organization_id)
                .with_for_update(read=True)
            )
            is None
        ):
            raise ConflictError("The original Organization is unavailable.")
        project = await self._session.scalar(
            select(ProjectRow)
            .where(
                ProjectRow.id == binding.project_id,
                ProjectRow.organization_id == binding.organization_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if project is None or project.status is not ProjectStatus.DELETING:
            raise ConflictError("The original Project is not blocked for deletion.")
        parent = await self._session.scalar(
            select(ProjectDeletionObligationRow)
            .where(ProjectDeletionObligationRow.id == binding.obligation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            parent is None
            or parent.job_id != context.job_id.value
            or PostgresJobBindingMapper.project_deletion(parent) != binding
        ):
            raise ConflictError("Shutdown has no matching retained original.")
        facts = ProjectDeletionShutdownFactsDTO(
            InstallationId(installed),
            OrganizationId(project.organization_id),
            ProjectId(project.id),
            project.status,
            project.access_revision,
            binding,
            parent.source_revision,
            parent.shutdown_completed_at,
        )
        self._transaction = self._session.sync_session.get_transaction()
        self._facts, self._context = facts, context
        return facts

    @override
    async def record_shutdown(
        self,
        context: JobAttemptContextDTO,
        *,
        facts: ProjectDeletionShutdownFactsDTO,
        changed: bool,
        access_revision: int,
    ) -> None:
        """Save local effects' revision/audit and monotonic parent checkpoint atomically.

        Use the same caller transaction, held coordination and live original
        fence. Recheck that fence and checked source revision before conditional
        persistence. Changed Access rows advance the revision once and require
        their correlated audit. An unchanged checked state advances no Access
        revision and creates no change audit. Both confirm local shutdown only.
        Do not settle physical cleanup, start retention, alter immutable original
        meaning, write generic completion bytes, commit or reset a deadline.
        Failure must propagate for rollback with the preceding effects.
        """
        if (
            self._transaction is None
            or self._session.sync_session.get_transaction() is not self._transaction
            or not self._session.is_active
            or self._facts != facts
            or self._context != context
        ):
            raise RuntimeError(
                "Checkpoint persistence requires its exact locked caller transaction."
            )
        binding = context.binding
        if (
            not isinstance(binding, ProjectDeletionJobBindingDTO)
            or type(changed) is not bool
            or access_revision != facts.access_revision + int(changed)
        ):
            raise ConflictError("The local shutdown result changed its checked revision.")
        try:
            await PostgresJobStore(self._session).require_current(context)
            revision = await self._session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == binding.project_id,
                    ProjectRow.organization_id == binding.organization_id,
                    ProjectRow.status == ProjectStatus.DELETING,
                )
            )
            if revision != facts.access_revision:
                raise ConflictError("The checked Project revision changed.")
            if changed:
                advanced = await self._session.scalar(
                    update(ProjectRow)
                    .where(
                        ProjectRow.id == binding.project_id,
                        ProjectRow.organization_id == binding.organization_id,
                        ProjectRow.status == ProjectStatus.DELETING,
                        ProjectRow.access_revision == facts.access_revision,
                    )
                    .values(access_revision=access_revision)
                    .returning(ProjectRow.id)
                )
                if advanced is None:
                    raise ConflictError("The local shutdown revision could not be confirmed.")
            live = exists().where(
                DurableJobRow.id == context.job_id.value,
                DurableJobRow.binding_kind == "project_deletion",
                DurableJobRow.deletion_obligation_id == binding.obligation_id,
                DurableJobRow.status == "running",
                DurableJobRow.attempt_count == context.attempt,
                DurableJobRow.fence == context.fence.value,
                DurableJobRow.work_deadline == context.work_deadline,
                DurableJobRow.lease_expires_at > func.clock_timestamp(),
                DurableJobRow.work_deadline > func.clock_timestamp(),
                DurableJobRow.pending_effect.is_(None),
            )
            saved = await self._session.scalar(
                update(ProjectDeletionObligationRow)
                .where(
                    ProjectDeletionObligationRow.id == binding.obligation_id,
                    ProjectDeletionObligationRow.job_id == context.job_id.value,
                    ProjectDeletionObligationRow.source_revision == facts.source_revision,
                    ProjectDeletionObligationRow.source_revision < 9007199254740991,
                    ProjectDeletionObligationRow.shutdown_completed_at.is_(None),
                    ProjectDeletionObligationRow.physical_cleanup_completed_at.is_(None),
                    live,
                )
                .values(
                    shutdown_completed_at=func.clock_timestamp(),
                    source_revision=facts.source_revision + 1,
                )
                .returning(ProjectDeletionObligationRow.id)
            )
            if saved is None:
                raise JobFenceLostError(
                    "The original local shutdown checkpoint lost its live fence."
                )
            if changed:
                self._session.add(
                    AccessAuditEventRow(
                        id=uuid4(),
                        organization_id=binding.organization_id,
                        project_id=binding.project_id,
                        actor_kind="human",
                        actor_principal_id=binding.initiator_principal_id,
                        event_type="project_applications_shutdown",
                        target_kind="project",
                        target_id=binding.project_id,
                        before_values={"access_revision": facts.access_revision},
                        after_values={"access_revision": access_revision},
                        correlation_id=binding.operation_id.value,
                    )
                )
            await self._session.flush()
        finally:
            self._facts = None
            self._context = None
            self._transaction = None
