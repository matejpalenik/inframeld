from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from inframeld_backend.access.application.dtos.project_departure_candidate_dto import (
    ProjectDepartureCandidateDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId


@dataclass(frozen=True, slots=True)
class ProjectDepartureResponsibilityDTO:
    """Bind candidate observations to an affected Project, group or application."""

    target_kind: Literal["project", "access_group", "application_account"]
    target_id: UUID
    action_id: ActionId | None
    requires_group_manager: bool
    allows_group_manager: bool
    candidates: tuple[ProjectDepartureCandidateDTO, ...]
