from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class CurrentApplicationSessionDTO:
    """Return only the current admitted application's identity and bound Project."""

    principal_id: PrincipalId
    project_id: ProjectId
