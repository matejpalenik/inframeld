from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.access.application.dtos.project_departure_candidate_dto import (
    ProjectDepartureCandidateDTO,
)
from inframeld_backend.access.domain.enums.project_departure_target_kind import (
    ProjectDepartureTargetKind,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId


@dataclass(frozen=True, slots=True)
class ProjectDepartureResponsibilityDTO:
    """Bind candidate observations to an affected Project, group or application."""

    target_kind: ProjectDepartureTargetKind
    target_id: UUID
    action_id: ActionId | None
    candidates: tuple[ProjectDepartureCandidateDTO, ...]
