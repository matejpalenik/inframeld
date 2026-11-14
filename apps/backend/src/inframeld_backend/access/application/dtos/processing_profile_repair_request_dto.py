from dataclasses import dataclass, field
from typing import Literal

from inframeld_backend.access.application.enums.repair_responsibility_kind import (
    RepairResponsibilityKind,
)
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)


@dataclass(frozen=True, slots=True)
class ProcessingProfileRepairRequestDTO:
    """Identify the requested Profile action before the reader resolves its Project."""

    processing_profile_id: ProcessingProfileId
    action: ProcessingProfileAction
    kind: Literal[RepairResponsibilityKind.ACTION_GRANTOR] = field(
        default=RepairResponsibilityKind.ACTION_GRANTOR, init=False
    )
