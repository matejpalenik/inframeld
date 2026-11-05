from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.project_action_facts_reader import (
    ProjectActionFactsReader,
)
from inframeld_backend.access.application.protocols.project_budget_authorizer import (
    ProjectBudgetAuthorizer,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.policies.action_authorization_policy import (
    ActionAuthorizationPolicy,
)
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.policy_inputs.action_authorization_policy_input import (
    ActionAuthorizationPolicyInput,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)

_BUDGET_ACTIONS = frozenset({ProjectAction.INSPECT_BUDGET.value, ProjectAction.MANAGE_BUDGET.value})


class ProjectBudgetAuthorizationService(ProjectBudgetAuthorizer):
    """Check budget inspection or human-only management from current Access facts."""

    def __init__(self, facts_reader: ProjectActionFactsReader) -> None:
        self._facts_reader = facts_reader

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: ProjectActionAuthorizationRequestDTO
    ) -> ProjectActionAuthorizationDTO:
        facts = await self._facts_reader.read_action_facts(
            access=access,
            action_id=request.action_id,
            target=ProjectActionTargetDTO(request.project_id),
        )
        if facts is None:
            raise ResourceNotFoundError()
        if facts.principal.id != access.actor_principal_id:
            raise RuntimeError("Authorization facts do not match the authenticated actor.")

        principal_access = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.principal,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
        )
        if not principal_access.credential_is_current:
            raise HumanOAuthCredentialRejectedError()

        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=facts.principal.status,
            project_status=facts.project_status,
            is_project_member=facts.is_project_member,
        ):
            raise ResourceNotFoundError()

        policy_input = ActionAuthorizationPolicyInput(
            principal_access=principal_access,
            is_project_member=facts.is_project_member,
            has_exact_action_grant=facts.has_exact_action_grant,
        )
        if (
            request.action_id.value not in _BUDGET_ACTIONS
            or not ProjectActionEligibilityPolicy.may_use(
                action_id=request.action_id, principal_kind=facts.principal.kind
            )
            or not ActionAuthorizationPolicy.may_perform_action(policy_input)
        ):
            raise AccessDeniedError()

        return ProjectActionAuthorizationDTO(facts.principal.organization_id, request.project_id)
