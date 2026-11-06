from dataclasses import dataclass

from inframeld_backend.access.application.dtos.access_group_metadata_dto import (
    AccessGroupMetadataDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class AccessGroupReadFactsDTO:
    installation_id: InstallationId
    group: AccessGroupMetadataDTO
    action: ProjectActionFactsDTO
    is_member: bool
    is_manager: bool
    has_group_action: bool
