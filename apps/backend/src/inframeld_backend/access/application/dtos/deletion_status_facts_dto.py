from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class DeletionStatusFactsDTO:
    """Report current eligibility independently of Project membership and deletion history."""

    installation_id: InstallationId
    principal: Principal
    has_pending_recovery: bool
    oauth_credential_facts: HumanCredentialFactsDTO | None
