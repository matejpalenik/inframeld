from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ApplicationAccountGrantTargetDTO:
    project_id: ProjectId
    application_principal_id: PrincipalId
