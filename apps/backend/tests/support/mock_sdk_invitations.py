"""Supply invitation wire outcomes without emulating provider, SQL or retained history."""

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
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_result_dto import (
    InvitationActivationResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_issue_result_dto import (
    InvitationIssueResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_preview_result_dto import (
    InvitationPreviewResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_access_revision_dto import (
    InvitationProjectAccessRevisionDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_revocation_result_dto import (
    InvitationRevocationResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_scope_dto import InvitationScopeDTO
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.invitation_activator import InvitationActivator
from inframeld_backend.access.application.protocols.invitation_issuer import InvitationIssuer
from inframeld_backend.access.application.protocols.invitation_previewer import InvitationPreviewer
from inframeld_backend.access.application.protocols.invitation_revoker import InvitationRevoker
from inframeld_backend.access.application.protocols.invitation_session_verifier import (
    InvitationSessionVerifier,
)
from inframeld_backend.access.application.queries.preview_invitation_query import (
    PreviewInvitationQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token import InvitationToken
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import ResourceNotFoundError
from inframeld_backend.shared.application.value_objects.operation_id import OperationId

_ORGANIZATION = OrganizationId(UUID("00000000-0000-4000-8000-000000000002"))
_PROJECT = ProjectId(UUID("00000000-0000-4000-8000-000000000003"))
_RECIPIENT = PrincipalId(UUID("00000000-0000-4000-8000-000000000004"))
_INVITATION = InvitationId(UUID("00000000-0000-4000-8000-000000000006"))
_GROUP = AccessGroupId(UUID("00000000-0000-4000-8000-000000000007"))
_ACCOUNT = PrincipalId(UUID("00000000-0000-4000-8000-000000000008"))
_EXPIRES = datetime(2030, 1, 1, tzinfo=UTC)
_TOKEN = InvitationToken("A" * 43)


class MockSDKInvitations(
    InvitationIssuer,
    InvitationRevoker,
    InvitationPreviewer,
    InvitationActivator,
    InvitationSessionVerifier,
):
    def __init__(self, identity: VerifiedHumanIdentityDTO) -> None:
        self._identity = identity

    @override
    async def verify(
        self, credential: BrowserSessionCredential, *, observe_password_completion: bool = False
    ) -> InvitationBrowserProofDTO | None:
        if credential.value != "sdk-cookie":
            return None
        return InvitationBrowserProofDTO(
            self._identity, True if observe_password_completion else None
        )

    @override
    async def issue(
        self,
        *,
        access: AccessContextDTO,
        command: IssueInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationIssueResultDTO:
        if command.organization_id != _ORGANIZATION:
            raise ResourceNotFoundError()
        replay = context.key.value == "sdk-invitation-replay"
        return InvitationIssueResultDTO(
            _INVITATION,
            _ORGANIZATION,
            command.assignments,
            _EXPIRES,
            8,
            CompletedSynchronousOperationDTO(
                OperationId("sdk-invitation-issue"),
                not replay,
                OperationReplayKind.ISSUED_SECRET,
                _EXPIRES,
            ),
            None if replay else _TOKEN,
        )

    @override
    async def revoke(
        self,
        *,
        access: AccessContextDTO,
        command: RevokeInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationRevocationResultDTO:
        if command.invitation_id != _INVITATION:
            raise ResourceNotFoundError()
        return InvitationRevocationResultDTO(
            _INVITATION,
            _ORGANIZATION,
            8,
            CompletedSynchronousOperationDTO(
                OperationId("sdk-invitation-revoke"),
                True,
                OperationReplayKind.SAFE_RESULT,
                _EXPIRES,
            ),
        )

    @override
    async def preview(
        self, *, proof: InvitationBrowserProofDTO, query: PreviewInvitationQuery
    ) -> InvitationPreviewResultDTO:
        if query.token != _TOKEN:
            raise ResourceNotFoundError()
        return InvitationPreviewResultDTO(
            _INVITATION,
            _ORGANIZATION,
            (
                InvitationProjectMembershipIntentDTO(_PROJECT),
                InvitationGroupMembershipIntentDTO(_PROJECT, _GROUP),
                InvitationGroupManagerIntentDTO(_PROJECT, _GROUP),
                InvitationActionGrantIntentDTO(
                    OrganizationGrantTargetDTO(_ORGANIZATION), ActionId("create-projects"), False
                ),
                InvitationActionGrantIntentDTO(
                    ProjectGrantTargetDTO(_PROJECT), ActionId("create-access-groups"), True
                ),
                InvitationActionGrantIntentDTO(
                    AccessGroupGrantTargetDTO(_PROJECT, _GROUP), ActionId("add-documents"), True
                ),
                InvitationActionGrantIntentDTO(
                    ApplicationAccountGrantTargetDTO(_PROJECT, _ACCOUNT),
                    ActionId("issue-application-keys"),
                    True,
                ),
            ),
            _EXPIRES,
            (
                InvitationScopeDTO(
                    OrganizationGrantTargetDTO(_ORGANIZATION), "Example Organization"
                ),
                InvitationScopeDTO(ProjectGrantTargetDTO(_PROJECT), "Example Project"),
                InvitationScopeDTO(AccessGroupGrantTargetDTO(_PROJECT, _GROUP), "Example Group"),
                InvitationScopeDTO(
                    ApplicationAccountGrantTargetDTO(_PROJECT, _ACCOUNT), "Example Account"
                ),
            ),
        )

    @override
    async def activate(
        self,
        *,
        proof: InvitationBrowserProofDTO,
        command: ActivateInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationActivationResultDTO:
        if command.token != _TOKEN:
            raise ResourceNotFoundError()
        return InvitationActivationResultDTO(
            _INVITATION,
            _ORGANIZATION,
            _RECIPIENT,
            8,
            (InvitationProjectAccessRevisionDTO(_PROJECT, 9),),
            CompletedSynchronousOperationDTO(
                OperationId("sdk-invitation-activate"),
                True,
                OperationReplayKind.SAFE_RESULT,
                _EXPIRES,
            ),
        )
