from dataclasses import dataclass

from inframeld_backend.access.application.dtos.application_account_metadata_dto import (
    ApplicationAccountMetadataDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ApplicationAccountReadFactsDTO:
    """Observe current caller authority and an exact account in one database snapshot."""

    installation_id: InstallationId
    action: ProjectActionFactsDTO
    account: ApplicationAccountMetadataDTO
    can_read_keys: bool
