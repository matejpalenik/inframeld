from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class InvitationActivationFactsDTO:
    """Observe recipient state and database-current UTC after identity and Access turns."""

    invitation: InvitationRecordDTO
    principal: Principal | None
    credential_state: HumanCredentialStateDTO
    has_credential_history: bool
    current_time: datetime
    organization_access_revision: int
    project_memberships: frozenset[ProjectId] = frozenset[ProjectId]()
