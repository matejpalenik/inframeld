from dataclasses import dataclass, field
from datetime import datetime

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.human_suspension_job_binding_dto import (
    HumanSuspensionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.domain.enums.job_status import JobStatus


@dataclass(frozen=True, slots=True)
class JobSnapshotDTO:
    """Observe durable execution facts without authorizing their use."""

    job_id: JobId
    binding: (
        ProductJobBindingDTO
        | ArtifactCleanupJobBindingDTO
        | ProjectDeletionJobBindingDTO
        | HumanSuspensionJobBindingDTO
    )
    payload: JobPayload
    status: JobStatus
    admitted_at: datetime
    queued_deadline: datetime
    due_at: datetime
    observed_at: datetime
    attempt: int
    work_deadline: datetime | None
    fence: JobFence | None
    lease_expires_at: datetime | None
    cancel_requested: bool
    pending_effect: str | None
    reason: str | None
    checkpoint: bytes = field(repr=False)
