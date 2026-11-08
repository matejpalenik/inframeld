from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_group_grant_management_facts_dto import (
    AccessGroupGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


class InvitationAccessGroupGrantWriter(Protocol):
    @abstractmethod
    async def apply_invitation_grant(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        facts: AccessGroupGrantManagementFactsDTO,
        recipient_principal_id: PrincipalId,
        after: ActionGrantState,
    ) -> int:
        """Persist the exact checked SET under the actual pending invitation binding.

        Share the native row transition, with current scope, before-state and
        revision guards. Preserve unchanged grants and original assignment
        attribution on level replacement. New assignments attribute the issuer.
        Return the resulting Access revision without a native receipt or commit."""
        ...
