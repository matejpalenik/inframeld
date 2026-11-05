from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.dtos.job_effect_binding_dto import JobEffectBindingDTO
from inframeld_backend.shared.application.enums.job_effect_observation_kind import (
    JobEffectObservationKind,
)


@dataclass(frozen=True, slots=True)
class JobEffectObservationDTO:
    """Observe retained admission and proof under database time, never permission."""

    binding: JobEffectBindingDTO
    observed_at: datetime
    admitted_at: datetime | None = None
    kind: JobEffectObservationKind | None = None
    aborted_at: datetime | None = None
    consumed_at: datetime | None = None
