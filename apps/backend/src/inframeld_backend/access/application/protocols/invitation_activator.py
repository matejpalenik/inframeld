from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.activate_invitation_command import (
    ActivateInvitationCommand,
)
from inframeld_backend.access.application.dtos.invitation_activation_result_dto import (
    InvitationActivationResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class InvitationActivator(Protocol):
    @abstractmethod
    async def activate(
        self,
        *,
        proof: InvitationBrowserProofDTO,
        command: ActivateInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationActivationResultDTO:
        """Recover an eligible same-recipient original or atomically activate fresh intent.

        Provider verification precedes SQL. Completed replay retains current identity
        and local eligibility, but requires no fresh password fact, issuer authority
        or valid-unused token and performs no state or audit write. Fresh execution
        preserves the identity, Organization and sorted Project coordination, exact
        promised effects and one atomic original result.
        """
        ...
