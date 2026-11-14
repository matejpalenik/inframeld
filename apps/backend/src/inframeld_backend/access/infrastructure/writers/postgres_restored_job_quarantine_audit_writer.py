from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.shared.application.commands.restored_job_quarantine_command import (
    RestoredJobQuarantineCommand,
)
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.errors.restored_job_quarantine_error import (
    RestoredJobQuarantineError,
)
from inframeld_backend.shared.domain.enums.job_status import JobStatus


class PostgresRestoredJobQuarantineAuditWriter:
    """Retain one operator event and match only its exact original maintenance request."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def matches_original(
        self, command: RestoredJobQuarantineCommand, job: JobSnapshotDTO
    ) -> bool:
        saved = await self._session.get(AccessAuditEventRow, UUID(command.operation_id.value))
        if saved is None:
            return False

        expected = self._event(command, job)
        if any(
            getattr(saved, name) != getattr(expected, name)
            for name in (
                "organization_id",
                "project_id",
                "actor_kind",
                "actor_principal_id",
                "actor_reference",
                "affected_principal_id",
                "event_type",
                "target_kind",
                "target_id",
                "action",
                "before_values",
                "after_values",
                "reason",
                "correlation_id",
            )
        ):
            raise RestoredJobQuarantineError("The maintenance audit does not match its original.")
        return True

    async def append(self, command: RestoredJobQuarantineCommand, job: JobSnapshotDTO) -> None:
        self._session.add(self._event(command, job))
        await self._session.flush()

    @staticmethod
    def _event(command: RestoredJobQuarantineCommand, job: JobSnapshotDTO) -> AccessAuditEventRow:
        binding = job.binding
        if not isinstance(binding, ProductJobBindingDTO) or command.expected_status is None:
            raise RestoredJobQuarantineError("The original audit binding is unavailable.")
        authority = binding.authority
        return AccessAuditEventRow(
            id=UUID(command.operation_id.value),
            organization_id=authority.organization_id.value,
            project_id=authority.project_id.value,
            actor_kind="operator",
            actor_reference=command.operator_label,
            event_type="job_restore_quarantined",
            target_kind="job",
            target_id=job.job_id.value,
            action=authority.action_id.value,
            before_values={
                "installation_id": str(authority.installation_id.value),
                "job_operation_id": binding.operation_id.value,
                "request_id": str(binding.request_id.value),
                "status": command.expected_status.value,
                "attempt": command.expected_attempt,
            },
            after_values={"status": JobStatus.RECOVERY_REQUIRED.value},
            reason=command.reason,
            correlation_id=command.operation_id.value,
        )
