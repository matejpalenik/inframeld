from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_grant_authorization_dto import (
    ProjectGrantAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_use_only_grant_authorization_request_dto import (
    ProjectUseOnlyGrantAuthorizationRequestDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.project_grant_authorizer import (
    ProjectGrantAuthorizer,
)
from inframeld_backend.access.application.protocols.project_grant_change_facts_reader import (
    ProjectGrantChangeFactsReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.policies.project_grant_delegation_policy import (
    ProjectGrantDelegationPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)


class ProjectGrantAuthorizationService(ProjectGrantAuthorizer):
    def __init__(self, facts_reader: ProjectGrantChangeFactsReader) -> None:
        self._facts_reader = facts_reader

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: ProjectUseOnlyGrantAuthorizationRequestDTO
    ) -> ProjectGrantAuthorizationDTO:
        facts = await self._facts_reader.read_for_change(
            access=access,
            project_id=request.project_id,
            recipient_principal_id=request.recipient_principal_id,
            action_id=request.action_id,
        )

        if facts is None:
            raise ResourceNotFoundError()

        actor_access = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.actor,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
        )
        if not actor_access.credential_is_current:
            raise HumanOAuthCredentialRejectedError()

        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=facts.actor.status,
            project_status=facts.project_status,
            is_project_member=facts.actor_is_project_member,
        ):
            raise ResourceNotFoundError()

        if not ProjectGrantDelegationPolicy.may_delegate_project_action(
            actor_access=actor_access,
            actor_is_project_member=facts.actor_is_project_member,
            actor_can_grant_action=facts.actor_can_grant_action,
        ):
            raise AccessDeniedError()

        if facts.recipient is None:
            raise ResourceNotFoundError()

        if not ProjectGrantDelegationPolicy.may_assign_use_only_to_human(
            actor_access=actor_access,
            recipient=facts.recipient,
            actor_is_project_member=facts.actor_is_project_member,
            recipient_is_project_member=facts.recipient_is_project_member,
            actor_can_grant_action=facts.actor_can_grant_action,
        ):
            raise AccessDeniedError()

        return ProjectGrantAuthorizationDTO(
            organization_id=facts.actor.organization_id,
            project_id=request.project_id,
            project_access_revision=facts.project_access_revision,
        )
