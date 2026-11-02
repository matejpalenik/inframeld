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
        jobs: ArtifactCleanupAdmissionWriter,
        audit: ArtifactCleanupAuditWriter,
        *,
        capacity: int = 8,
    ) -> None:
        self._jobs = jobs
        self._audit = audit
        self._capacity = capacity

    async def admit(self, binding: ArtifactCleanupJobBindingDTO) -> ArtifactCleanupAdmissionDTO:
        admission = await self._jobs.admit(binding, capacity=self._capacity)
        if admission.created:
            await self._audit.append(admission, binding)
        return admission
