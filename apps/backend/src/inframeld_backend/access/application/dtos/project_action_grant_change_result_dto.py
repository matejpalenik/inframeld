from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectActionGrantChangeResultDTO:
    """Retain the original result independently of a later assignment or membership."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    actor_principal_id: PrincipalId
    recipient_principal_id: PrincipalId
    action_id: ActionId
    change_kind: Literal["set", "remove"]
    can_grant: bool | None
    access_revision: int
    changed: bool
    status_code: int
    operation: CompletedSynchronousOperationDTO
