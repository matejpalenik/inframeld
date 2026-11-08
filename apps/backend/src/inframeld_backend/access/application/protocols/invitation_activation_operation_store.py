from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_result_dto import (
    InvitationActivationResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_access_revision_dto import (
    InvitationProjectAccessRevisionDTO,
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
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class InvitationActivationOperationStore(Protocol):
    @abstractmethod
    async def read_activation_original(
        self,
        *,
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
        organization_id: OrganizationId,
        invitation_id: InvitationId,
        principal_id: PrincipalId | None,
        context: IdempotencyContextDTO,
        fingerprint: RequestFingerprint,
    ) -> InvitationActivationResultDTO | None:
        """Read only the exact live original after current recipient eligibility.

        The namespace is identity, Organization, method, route and key, with exact
        invitation/token meaning fingerprint-bound. Never renew its independent
        captured completion expiry or depend on ordinary issuance history.
        """
        ...

    @abstractmethod
    async def reserve_activation(
        self,
        *,
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
        invitation: InvitationRecordDTO,
        principal_id: PrincipalId | None,
        context: IdempotencyContextDTO,
        fingerprint: RequestFingerprint,
    ) -> InvitationActivationBindingDTO:
        """Reserve the exact pending namespace inside the coordinated caller transaction."""
        ...

    @abstractmethod
    async def bind_activation_principal(
        self, *, binding: InvitationActivationBindingDTO, principal: Principal
    ) -> InvitationActivationBindingDTO:
        """Bind the one actual flushed identity/principal without changing its original meaning."""
        ...

    @abstractmethod
    async def complete_activation(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        digest: InvitationTokenDigest,
        organization_access_revision: int,
        project_access_revisions: tuple[InvitationProjectAccessRevisionDTO, ...],
    ) -> InvitationActivationResultDTO:
        """Consume conditionally and retain the safe original, audit and one completion expiry.

        Require unused exact intent with expires_at > database clock_timestamp().
        Capture the independent 24-hour expiry once at database completion time,
        never transaction-start time or replay. Completed principal/result/expiry
        are required. Provider work and independent commit are forbidden here.
        """
        ...
