from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.job_effect_observation_dto import (
    JobEffectObservationDTO,
)
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.enums.job_continuation_disposition import (
    JobContinuationDisposition,
)


@dataclass(frozen=True, slots=True)
class JobContinuationEligibilityDTO:
    """Describe this assessed original job, not a reusable continuation permit."""

    job: JobSnapshotDTO
    disposition: JobContinuationDisposition
    reason: str
    observation: JobEffectObservationDTO | None = None
