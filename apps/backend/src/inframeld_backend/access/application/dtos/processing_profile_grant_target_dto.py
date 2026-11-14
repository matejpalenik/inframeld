from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)


@dataclass(frozen=True, slots=True)
class ProcessingProfileGrantTargetDTO:
    project_id: ProjectId
    processing_profile_id: ProcessingProfileId
