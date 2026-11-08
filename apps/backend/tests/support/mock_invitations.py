from datetime import UTC, datetime
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.activate_invitation_command import (
    ActivateInvitationCommand,
)
from inframeld_backend.access.application.commands.issue_invitation_command import (
    IssueInvitationCommand,
)
from inframeld_backend.access.application.commands.revoke_invitation_command import (
    RevokeInvitationCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.invitation_activation_result_dto import (
    InvitationActivationResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_admission_only_intent_dto import (
    InvitationAdmissionOnlyIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.dtos.invitation_issue_result_dto import (
    InvitationIssueResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_preview_result_dto import (
    InvitationPreviewResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_revocation_result_dto import (
    InvitationRevocationResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_scope_dto import InvitationScopeDTO
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.invitation_activator import InvitationActivator
from inframeld_backend.access.application.protocols.invitation_issuer import InvitationIssuer
from inframeld_backend.access.application.protocols.invitation_previewer import InvitationPreviewer
from inframeld_backend.access.application.protocols.invitation_revoker import InvitationRevoker
from inframeld_backend.access.application.queries.preview_invitation_query import (
    PreviewInvitationQuery,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token import InvitationToken
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_error import ApplicationError
from inframeld_backend.shared.application.value_objects.operation_id import OperationId

PROOF = InvitationBrowserProofDTO(
    VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject(str(UUID(int=1)))),
    None,
)
ORG = OrganizationId(UUID(int=1))
INVITATION = InvitationId(UUID(int=2))
RECIPIENT = PrincipalId(UUID(int=3))
TOKEN = InvitationToken("A" * 43)
EXPIRY = datetime(2030, 1, 1, tzinfo=UTC)


class MockInvitations(
    InvitationIssuer, InvitationRevoker, InvitationPreviewer, InvitationActivator
):
    """Return controlled workflow outcomes while observing exact transport mappings."""

    def __init__(self, *, replay: bool = False) -> None:
        operation = CompletedSynchronousOperationDTO(
            OperationId("invitation-original"), not replay, OperationReplayKind.SAFE_RESULT, EXPIRY
        )
        intents = (InvitationAdmissionOnlyIntentDTO(),)
        self.issued = InvitationIssueResultDTO(
            INVITATION, ORG, intents, EXPIRY, 8, operation, None if replay else TOKEN
        )
        self.revoked = InvitationRevocationResultDTO(INVITATION, ORG, 9, operation)
        self.previewed = InvitationPreviewResultDTO(
            INVITATION,
            ORG,
            intents,
            EXPIRY,
            (InvitationScopeDTO(OrganizationGrantTargetDTO(ORG), "Example Organization"),),
        )
        self.activated = InvitationActivationResultDTO(
            INVITATION, ORG, RECIPIENT, 10, (), operation
        )
        self.calls: list[tuple[object, ...]] = []
        self.error: ApplicationError | None = None

    @override
    async def issue(
        self,
        *,
        access: AccessContextDTO,
        command: IssueInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationIssueResultDTO:
        self.calls.append(("issue", access, command, context))
        if self.error is not None:
            raise self.error
        return self.issued

    @override
    async def revoke(
        self,
        *,
        access: AccessContextDTO,
        command: RevokeInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationRevocationResultDTO:
        self.calls.append(("revoke", access, command, context))
        if self.error is not None:
            raise self.error
        return self.revoked

    @override
    async def preview(
        self, *, proof: InvitationBrowserProofDTO, query: PreviewInvitationQuery
    ) -> InvitationPreviewResultDTO:
        self.calls.append(("preview", proof, query))
        if self.error is not None:
            raise self.error
        return self.previewed

    @override
    async def activate(
        self,
        *,
        proof: InvitationBrowserProofDTO,
        command: ActivateInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationActivationResultDTO:
        self.calls.append(("activate", proof, command, context))
        if self.error is not None:
            raise self.error
        return self.activated
