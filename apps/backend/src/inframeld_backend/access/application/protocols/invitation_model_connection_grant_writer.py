from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_facts_dto import (
    ModelConnectionGrantFactsDTO,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


class InvitationModelConnectionGrantWriter(Protocol):
    @abstractmethod
    async def apply_invitation_grant(
        self,
        binding: InvitationActivationBindingDTO,
        facts: ModelConnectionGrantFactsDTO,
        recipient: PrincipalId,
        after: ActionGrantState,
    ) -> int: ...
