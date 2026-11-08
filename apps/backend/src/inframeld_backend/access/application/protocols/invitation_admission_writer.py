from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_facts_dto import (
    InvitationActivationFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_issuer_facts_dto import (
    InvitationIssuerFactsDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal


class InvitationAdmissionWriter(Protocol):
    @abstractmethod
    async def apply_invitation_admission(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        facts: InvitationActivationFactsDTO,
        issuer: InvitationIssuerFactsDTO,
        principal: Principal,
    ) -> int:
        """Validate the pending activation and reuse the checked admission transition.

        The caller holds identity then Organization coordination and checked current
        recipient and issuer authority. Preserve native entry guards separately.
        New admission alone can initialize an absent version without history. No-op
        admission preserves credential state. Return the resulting Organization
        revision, with Alice attribution and Bob's activation correlation.
        """
        ...
