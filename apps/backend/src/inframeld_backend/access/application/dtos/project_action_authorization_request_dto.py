from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ProjectActionAuthorizationRequestDTO:
    """Name the exact project action selected by the trusted application workflow."""

    project_id: ProjectId
    action_id: ActionId
