from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


class InvitationProjectMembershipWriter(Protocol):
    @abstractmethod
    async def apply_invitation_membership(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        facts: ProjectMembershipChangeFactsDTO,
        principal_id: PrincipalId,
    ) -> int:
        """Apply only the promised ADD after exact pending binding and current scoped facts.

        Share the native checked membership transition, flushing prerequisites for
        subsequent assignments. Preserve no-op state, attribution and the Project
        revision. No ordinary native reservation or receipt is manufactured."""
        ...
