from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from inframeld_backend.shared.application.dtos.human_suspension_job_binding_dto import (
    HumanSuspensionJobBindingDTO,
)
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload


@dataclass(frozen=True, slots=True)
class HumanSuspensionJobFactsDTO:
    """Observe the original cleanup binding and the caller's live attempt."""

    binding: HumanSuspensionJobBindingDTO
    payload: JobPayload
    attempt: int
    fence: JobFence
    worker_id: UUID
    work_deadline: datetime
    lease_expires_at: datetime
    observed_at: datetime
    source_revision: int
