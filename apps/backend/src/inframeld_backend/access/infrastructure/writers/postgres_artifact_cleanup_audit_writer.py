from typing import override
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.shared.application.dtos.artifact_cleanup_admission_dto import (
    ArtifactCleanupAdmissionDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.business_operation_artifact_origin_dto import (
    BusinessOperationArtifactOriginDTO,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_audit_writer import (
    ArtifactCleanupAuditWriter,
)


class PostgresArtifactCleanupAuditWriter(ArtifactCleanupAuditWriter):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def append(
        self, admission: ArtifactCleanupAdmissionDTO, binding: ArtifactCleanupJobBindingDTO
    ) -> None:
        if (
            not self._session.in_transaction()
            or not admission.created
            or admission.obligation_id != binding.obligation_id
        ):
            raise RuntimeError("Audit only original cleanup admission in its caller transaction.")
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=binding.scope.organization_id.value,
                project_id=binding.scope.project_id.value,
                actor_kind="system_obligation",
                actor_reference=str(binding.obligation_id.value),
                event_type="artifact_cleanup_admitted",
                target_kind="job",
                target_id=admission.job_id.value,
                correlation_id=binding.origin.operation_id.value
                if isinstance(binding.origin, BusinessOperationArtifactOriginDTO)
                else None,
                after_values={
                    "request_id": str(binding.origin.request_id.value),
                    "obligation_id": str(binding.obligation_id.value),
                    "cleanup_kind": binding.kind.value,
                },
            )
        )
        await self._session.flush()
