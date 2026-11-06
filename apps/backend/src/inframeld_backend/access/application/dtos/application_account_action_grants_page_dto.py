from dataclasses import dataclass

from inframeld_backend.access.application.dtos.application_account_action_grant_dto import (
    ApplicationAccountActionGrantDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ApplicationAccountActionGrantsPageDTO:
    project_id: ProjectId
    application_principal_id: PrincipalId
    action_id: ActionId
    items: tuple[ApplicationAccountActionGrantDTO, ...]
    next_cursor: str | None
