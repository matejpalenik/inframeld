from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.invitation_scope_dto import InvitationScopeDTO
from inframeld_backend.access.domain.entities.principal import Principal


@dataclass(frozen=True, slots=True)
class InvitationPreviewFactsDTO:
    """Observe retained intent, current recipient eligibility and exact safe target labels."""

    invitation: InvitationRecordDTO
    principal: Principal | None
    credential_state: HumanCredentialStateDTO
    has_credential_history: bool
    scopes: tuple[InvitationScopeDTO, ...] | None
