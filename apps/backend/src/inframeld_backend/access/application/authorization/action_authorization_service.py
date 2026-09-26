"""Coordinate current fact retrieval, project visibility, and action admission."""

from typing import override

from inframeld_backend.access.application.access_context import AccessContext
from inframeld_backend.access.application.authorization.action_facts_reader import ActionFactsReader
from inframeld_backend.access.application.authorization.project_action_target import (
    ProjectActionTarget,
)
from inframeld_backend.access.application.authorization.require_action import RequireAction
from inframeld_backend.access.domain.action_authorization_policy import (
    ActionAuthorizationFacts,
    may_perform_action,
)
from inframeld_backend.access.domain.action_values import ActionId
from inframeld_backend.access.domain.principal import PrincipalStatus
from inframeld_backend.access.domain.project_visibility_policy import may_view_project
from inframeld_backend.shared.application.errors import AccessDeniedError, ResourceNotFoundError


class ActionAuthorizationService(RequireAction):
    """Hide unavailable projects, then require the caller's exact action authority."""

    def __init__(self, facts_reader: ActionFactsReader) -> None:
        """Use the reader bound to the caller's operation and transaction."""
        self._facts_reader = facts_reader

    @override
    async def require_action(
        self, *, access: AccessContext, action: ActionId, target: ProjectActionTarget
    ) -> None:
        """Apply visibility before action admission to preserve the 404/403 distinction."""
        facts = await self._facts_reader.read_action_facts(
            access=access, action=action, target=target
        )

        if facts is None or not may_view_project(
            principal_status=facts.principal_status,
            project_status=facts.project_status,
            is_project_member=facts.is_project_member,
        ):
            raise ResourceNotFoundError()

        authorization = ActionAuthorizationFacts(
            principal_is_active=facts.principal_status is PrincipalStatus.ACTIVE,
            is_project_member=facts.is_project_member,
            has_exact_action_grant=facts.has_exact_action_grant,
        )

        if not may_perform_action(authorization):
            raise AccessDeniedError()
