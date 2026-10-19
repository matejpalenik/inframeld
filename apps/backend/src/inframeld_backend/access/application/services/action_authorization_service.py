from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.protocols.action_authorizer import ActionAuthorizer
from inframeld_backend.access.application.protocols.project_action_facts_reader import (
    ProjectActionFactsReader,
)
from inframeld_backend.access.domain.policies.action_authorization_policy import (
    ActionAuthorizationPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.policy_inputs.action_authorization_policy_input import (
    ActionAuthorizationPolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)


class ActionAuthorizationService(ActionAuthorizer):
    """Hide unavailable projects, then require current eligibility and action authority."""

    def __init__(self, facts_reader: ProjectActionFactsReader) -> None:
        self._facts_reader = facts_reader

    @override
    async def require_action(
        self, *, access: AccessContextDTO, action_id: ActionId, target: ProjectActionTargetDTO
    ) -> OrganizationId:
        facts = await self._facts_reader.read_action_facts(
            access=access, action_id=action_id, target=target
        )

        if facts is None or not ProjectVisibilityPolicy.may_view_project(
            principal_status=facts.principal_access.principal.status,
            project_status=facts.project_status,
            is_project_member=facts.is_project_member,
        ):
            raise ResourceNotFoundError()

        policy_input = ActionAuthorizationPolicyInput(
            principal_access=facts.principal_access,
            is_project_member=facts.is_project_member,
            has_exact_action_grant=facts.has_exact_action_grant,
        )

        if not ActionAuthorizationPolicy.may_perform_action(policy_input):
            raise AccessDeniedError()

        return facts.principal_access.principal.organization_id
