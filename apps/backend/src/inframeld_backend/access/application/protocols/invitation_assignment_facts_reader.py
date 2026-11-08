from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.invitation_activation_facts_dto import (
    InvitationActivationFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_state_dto import (
    InvitationAssignmentStateDTO,
)
from inframeld_backend.access.application.dtos.invitation_issuer_facts_dto import (
    InvitationIssuerFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)


class InvitationAssignmentFactsReader(Protocol):
    @abstractmethod
    async def lock_for_activation(
        self, *, identity: VerifiedHumanIdentityDTO, digest: InvitationTokenDigest
    ) -> InvitationActivationFactsDTO | None:
        """Take identity then Organization and sorted Project turns in the caller transaction.

        Use READ COMMITTED and reread decision facts and database-current UTC after
        waits. Missing target rows do not prevent current-recipient original lookup.
        This observation does not apply fresh validity, password or issuer policy.
        """
        ...

    @abstractmethod
    async def read_current_issuer(
        self, *, invitation: InvitationRecordDTO
    ) -> InvitationIssuerFactsDTO | None:
        """Observe fresh issuer authority by retained PrincipalId after original lookup.

        Read active-account, exact human identity/coherence/recovery and complete
        intended delegation facts under existing turns. No authenticated issuer
        context, provider call or original issuance credential belongs here.
        """
        ...

    @abstractmethod
    async def read_assignment_states(
        self, *, invitation: InvitationRecordDTO, recipient: Principal | None
    ) -> tuple[InvitationAssignmentStateDTO, ...] | None:
        """Observe complete current native state before any activation effect.

        Preserve the exact intent order and honest absent-recipient/prerequisite
        facts. A missing real scope returns None, never a reduced inventory.
        The retained issuer is observed by PrincipalId, without a credential.
        """
        ...

    @abstractmethod
    async def read_assignment_state(
        self, *, invitation_id: InvitationId, recipient: Principal, intent: InvitationAssignmentDTO
    ) -> InvitationAssignmentStateDTO | None:
        """Reread one actual state after flushed prerequisites in the same coordinated caller turn."""
        ...
