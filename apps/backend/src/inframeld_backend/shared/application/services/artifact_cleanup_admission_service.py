from inframeld_backend.shared.application.dtos.artifact_cleanup_admission_dto import (
    ArtifactCleanupAdmissionDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_admission_writer import (
    ArtifactCleanupAdmissionWriter,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_audit_writer import (
    ArtifactCleanupAuditWriter,
)


class ArtifactCleanupAdmissionService:
    """Keep original obligation admission and required audit in the caller transaction."""

    def __init__(
        self,
        artifact_cleanup_admission_writer: ArtifactCleanupAdmissionWriter,
        artifact_cleanup_audit_writer: ArtifactCleanupAuditWriter,
        *,
        capacity: int = 8,
    ) -> None:
        self._artifact_cleanup_admission_writer = artifact_cleanup_admission_writer
        self._artifact_cleanup_audit_writer = artifact_cleanup_audit_writer
        self._capacity = capacity

    async def admit(self, binding: ArtifactCleanupJobBindingDTO) -> ArtifactCleanupAdmissionDTO:
        admission = await self._artifact_cleanup_admission_writer.admit(
            binding, capacity=self._capacity
        )
        if admission.created:
            await self._artifact_cleanup_audit_writer.append(admission, binding)
        return admission
