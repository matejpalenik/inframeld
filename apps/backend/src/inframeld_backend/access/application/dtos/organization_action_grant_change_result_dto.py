from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class OrganizationActionGrantChangeResultDTO:
    """Retain the original effect independently of today's Organization assignment."""

    installation_id: InstallationId
    organization_id: OrganizationId
    actor_principal_id: PrincipalId
    recipient_principal_id: PrincipalId
    action_id: ActionId
    method: Literal[HttpMethod.PUT, HttpMethod.DELETE]
    can_grant: bool | None
    access_revision: int
    changed: bool
    status_code: int
    operation: CompletedSynchronousOperationDTO
