from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_grant_authorization_dto import (
    ProjectGrantAuthorizationDTO,
)
from inframeld_backend.access.application.protocols.project_grant_authorizer import (
    ProjectGrantAuthorizer,
)
from inframeld_backend.access.application.protocols.project_grant_change_facts_reader import (
    ProjectGrantChangeFactsReader,
)
from inframeld_backend.access.domain.policies.project_grant_delegation_policy import (
    ProjectGrantDelegationPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)


class ProjectGrantAuthorizationService(ProjectGrantAuthorizer):
    """Coordinate current grant facts, project visibility and delegation policy."""

    def __init__(self, facts_reader: ProjectGrantChangeFactsReader) -> None:
        self._facts_reader = facts_reader

    @override
    async def require_use_only_assignment(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectGrantAuthorizationDTO:
        facts = await self._facts_reader.read_for_change(
            access=access,
            project_id=project_id,
            recipient_principal_id=recipient_principal_id,
            action_id=action_id,
        )

        if facts is None or not ProjectVisibilityPolicy.may_view_project(
            principal_status=facts.actor_access.principal.status,
            project_status=facts.project_status,
            is_project_member=facts.actor_is_project_member,
        ):
            raise ResourceNotFoundError()

        if not ProjectGrantDelegationPolicy.may_delegate_project_action(
            actor_access=facts.actor_access,
            actor_is_project_member=facts.actor_is_project_member,
            actor_can_grant_action=facts.actor_can_grant_action,
        ):
            raise AccessDeniedError()

        if facts.recipient is None:
            raise ResourceNotFoundError()

        if not ProjectGrantDelegationPolicy.may_assign_use_only_to_human(
            actor_access=facts.actor_access,
            recipient=facts.recipient,
            actor_is_project_member=facts.actor_is_project_member,
            recipient_is_project_member=facts.recipient_is_project_member,
            actor_can_grant_action=facts.actor_can_grant_action,
        ):
            raise AccessDeniedError()

        return ProjectGrantAuthorizationDTO(
            organization_id=facts.actor_access.principal.organization_id,
            project_access_revision=facts.project_access_revision,
        )
