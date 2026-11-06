from dataclasses import dataclass

from inframeld_backend.access.application.dtos.organization_action_grant_assignment_dto import (
    OrganizationActionGrantAssignmentDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


@dataclass(frozen=True, slots=True)
class OrganizationActionGrantsPageDTO:
    organization_id: OrganizationId
    action_id: ActionId
    items: tuple[OrganizationActionGrantAssignmentDTO, ...]
    next_cursor: str | None
