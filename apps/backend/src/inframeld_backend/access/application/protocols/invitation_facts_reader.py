from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.issue_invitation_command import (
    IssueInvitationCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.invitation_facts_dto import InvitationFactsDTO
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.invitation_revocation_facts_dto import (
    InvitationRevocationFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_revocation_result_dto import (
    InvitationRevocationResultDTO,
)
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class InvitationFactsReader(Protocol):
    """Observe retained intent without replacing current authorization or validity checks."""

    @abstractmethod
    async def read_by_digest(self, digest: InvitationTokenDigest) -> InvitationRecordDTO | None:
        """Resolve verification material without depending on issuance retry-history retention."""
        ...

    @abstractmethod
    async def lock_for_issue(
        self, *, access: AccessContextDTO, command: IssueInvitationCommand
    ) -> InvitationFactsDTO | None:
        """Observe all issuer/target facts after Org then sorted Project turns, without deciding authority."""
        ...

    @abstractmethod
    async def read_issue_original(
        self,
        *,
        organization_id: OrganizationId,
        issuer_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> InvitationRecordDTO | None:
        """Read original metadata only after current authority and exact reservation recovery."""
        ...

    @abstractmethod
    async def lock_for_revocation(
        self, *, access: AccessContextDTO, invitation_id: InvitationId
    ) -> InvitationRevocationFactsDTO | None:
        """Observe the same-Organization invitation and current actor after its exclusive turn.

        Require an active READ COMMITTED caller transaction. Keep assignment
        authority and fresh token validity out of these administration observations.
        """
        ...

    @abstractmethod
    async def read_revocation_original(
        self,
        *,
        organization_id: OrganizationId,
        actor_principal_id: PrincipalId,
        invitation_id: InvitationId,
        operation_id: OperationId,
    ) -> InvitationRevocationResultDTO | None:
        """Recover only the exact native safe result after current revocation authorization."""
        ...
