"""Coordinate current fact retrieval, project visibility, and action admission."""

from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.protocols.action_authorizer import ActionAuthorizer
from inframeld_backend.access.application.protocols.project_action_facts_reader import (
    ProjectActionFactsReader,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
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
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)


class ActionAuthorizationService(ActionAuthorizer):
    """Hide unavailable projects, then require the caller's exact action authority."""

    def __init__(self, facts_reader: ProjectActionFactsReader) -> None:
        """Use the reader bound to the caller's operation and transaction."""
        self._facts_reader = facts_reader

    @override
    async def require_action(
        self, *, access: AccessContextDTO, action: ActionId, target: ProjectActionTargetDTO
    ) -> None:
        """Apply visibility before action admission to preserve the 404/403 distinction."""
        facts = await self._facts_reader.read_action_facts(
            access=access, action=action, target=target
        )

        if facts is None or not ProjectVisibilityPolicy.may_view_project(
            principal_status=facts.principal_status,
            project_status=facts.project_status,
            is_project_member=facts.is_project_member,
        ):
            raise ResourceNotFoundError()

        policy_input = ActionAuthorizationPolicyInput(
            principal_is_active=facts.principal_status is PrincipalStatus.ACTIVE,
            is_project_member=facts.is_project_member,
            has_exact_action_grant=facts.has_exact_action_grant,
        )

        if not ActionAuthorizationPolicy.may_perform_action(policy_input):
            raise AccessDeniedError()
