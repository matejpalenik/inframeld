from dataclasses import dataclass

from inframeld_backend.access.application.dtos.application_key_current_facts_dto import (
    ApplicationKeyCurrentFactsDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ApplicationAuthenticationFactsDTO:
    """Observe the current account and its required Project relationship without grants."""

    principal: Principal
    project_id: ProjectId
    project_status: ProjectStatus
    is_project_member: bool
    has_coherent_binding: bool
    key_facts: ApplicationKeyCurrentFactsDTO | None = None
