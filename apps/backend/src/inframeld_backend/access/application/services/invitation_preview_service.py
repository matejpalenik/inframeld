import asyncio
from datetime import UTC, datetime
from typing import override

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_admission_only_intent_dto import (
    InvitationAdmissionOnlyIntentDTO,
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
from inframeld_backend.access.application.dtos.invitation_model_connection_target_dto import (
    InvitationModelConnectionTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_preview_result_dto import (
    InvitationPreviewResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.invitation_target_dto import InvitationTargetDTO
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.protocols.invitation_preview_facts_reader import (
    InvitationPreviewFactsReader,
)
from inframeld_backend.access.application.protocols.invitation_previewer import InvitationPreviewer
from inframeld_backend.access.application.queries.preview_invitation_query import (
    PreviewInvitationQuery,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.access_group_grant_policy import (
    AccessGroupGrantPolicy,
)
from inframeld_backend.access.domain.policies.application_account_grant_policy import (
    ApplicationAccountGrantPolicy,
)
from inframeld_backend.access.domain.policies.human_admission_policy import HumanAdmissionPolicy
from inframeld_backend.access.domain.policies.invitation_policy import InvitationPolicy
from inframeld_backend.access.domain.policies.organization_grant_policy import (
    OrganizationGrantPolicy,
)
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class InvitationPreviewService(InvitationPreviewer):
    """Present bounded intended scope without admitting or assigning the recipient."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        invitation_preview_facts_reader: InvitationPreviewFactsReader,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._invitation_preview_facts_reader = invitation_preview_facts_reader

    @override
    async def preview(
        self, *, proof: InvitationBrowserProofDTO, query: PreviewInvitationQuery
    ) -> InvitationPreviewResultDTO:
        digest = query.token.digest()
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._invitation_preview_facts_reader.read_preview(
                    identity=proof.identity, digest=digest
                )
                if facts is None:
                    raise ResourceNotFoundError()
                invitation = facts.invitation
                if not invitation.digest.matches(digest):
                    raise RuntimeError("Preview facts changed the protected invitation binding.")
                if not InvitationPolicy.may_consume(
                    expires_at=invitation.expires_at,
                    current_time=datetime.now(UTC),
                    revoked_at=invitation.revoked_at,
                    consumed_at=invitation.consumed_at,
                ):
                    raise ResourceNotFoundError()

                state = facts.credential_state
                if state.identity != proof.identity:
                    raise RuntimeError("Preview facts changed the verified recipient identity.")
                if not HumanAdmissionPolicy.may_admit(
                    principal=facts.principal,
                    organization_id=invitation.organization_id,
                    has_pending_recovery=state.has_pending_recovery,
                ):
                    raise ConflictError("The invitation recipient is not currently admissible.")
                if state.version is None and facts.has_credential_history:
                    raise DependencyUnavailableError()
                if facts.scopes is None:
                    raise ConflictError("The intended invitation scope is no longer available.")
                required = self._required_targets(invitation)
                observed = {scope.target for scope in facts.scopes}
                for scope in facts.scopes:
                    if isinstance(scope.target, InvitationModelConnectionTargetDTO):
                        if scope.model_project_id is None:
                            raise RuntimeError(
                                "Preview lost the model connection's owning Project."
                            )
                        required.add(ProjectGrantTargetDTO(scope.model_project_id))
                    elif scope.model_project_id is not None:
                        raise RuntimeError("Preview attached a model binding to another target.")
                if (
                    len(facts.scopes) > 201
                    or len(observed) != len(facts.scopes)
                    or observed != required
                ):
                    raise RuntimeError("Preview labels changed the exact intended scope.")
                return InvitationPreviewResultDTO(
                    invitation_id=invitation.invitation_id,
                    organization_id=invitation.organization_id,
                    assignments=invitation.assignments,
                    expires_at=invitation.expires_at,
                    scopes=facts.scopes,
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _required_targets(invitation: InvitationRecordDTO) -> set[InvitationTargetDTO]:
        targets: set[InvitationTargetDTO] = {
            OrganizationGrantTargetDTO(organization_id=invitation.organization_id)
        }
        for intent in invitation.assignments:
            if isinstance(intent, InvitationAdmissionOnlyIntentDTO):
                continue
            if isinstance(intent, InvitationProjectMembershipIntentDTO):
                targets.add(ProjectGrantTargetDTO(project_id=intent.project_id))
                continue
            if isinstance(
                intent, (InvitationGroupMembershipIntentDTO, InvitationGroupManagerIntentDTO)
            ):
                targets.add(ProjectGrantTargetDTO(project_id=intent.project_id))
                targets.add(
                    AccessGroupGrantTargetDTO(
                        project_id=intent.project_id, access_group_id=intent.access_group_id
                    )
                )
                continue
            target = intent.target
            if isinstance(target, OrganizationGrantTargetDTO):
                supported = (
                    target.organization_id == invitation.organization_id
                    and OrganizationGrantPolicy.supports_action(intent.action_id)
                )
            elif isinstance(target, ProjectGrantTargetDTO):
                supported = ProjectActionEligibilityPolicy.may_use(
                    action_id=intent.action_id, principal_kind=PrincipalKind.HUMAN
                )
            elif isinstance(target, AccessGroupGrantTargetDTO):
                supported = AccessGroupGrantPolicy.supports_recipient(
                    action_id=intent.action_id, kind=PrincipalKind.HUMAN, can_grant=intent.can_grant
                )
            elif isinstance(target, ApplicationAccountGrantTargetDTO):
                supported = ApplicationAccountGrantPolicy.supports_recipient(
                    action_id=intent.action_id, kind=PrincipalKind.HUMAN
                )
            elif isinstance(target, InvitationModelConnectionTargetDTO):
                supported = intent.action_id.value in ModelConnectionAction
            else:
                # Real future owners add their authoritative integration, never a placeholder target.
                supported = False
            if not supported:
                raise ConflictError("The intended invitation effect is not currently supported.")
            if isinstance(
                target,
                (
                    ProjectGrantTargetDTO,
                    AccessGroupGrantTargetDTO,
                    ApplicationAccountGrantTargetDTO,
                ),
            ):
                targets.add(ProjectGrantTargetDTO(project_id=target.project_id))
            targets.add(target)
        return targets
