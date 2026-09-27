from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
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
from inframeld_backend.shared.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)


class ProjectGrantChangeService:
    """Coordinate a project grant change using current, locked Access facts."""

    def __init__(self, facts_reader: ProjectGrantChangeFactsReader) -> None:
        self._facts_reader = facts_reader

    async def assign_use_only(
        self,
        *,
        access: AccessContextDTO,
        request: ProjectOperationAdmissionRequestDTO,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
        expected_access_revision: int,
    ) -> None:
        facts = await self._facts_reader.read_for_change(
            access=access,
            project_id=request.project_id,
            recipient_principal_id=recipient_principal_id,
            action_id=action_id,
        )

        if facts is None or not ProjectVisibilityPolicy.may_view_project(
            principal_status=facts.actor.status,
            project_status=facts.project_status,
            is_project_member=facts.actor_is_project_member,
        ):
            raise ResourceNotFoundError

        if not ProjectGrantDelegationPolicy.may_delegate_project_action(
            actor=facts.actor,
            actor_is_project_member=facts.actor_is_project_member,
            actor_can_grant_action=facts.actor_can_grant_action,
        ):
            raise AccessDeniedError

        if facts.recipient is None:
            raise ResourceNotFoundError

        if not ProjectGrantDelegationPolicy.may_assign_use_only_to_human(
            actor=facts.actor,
            recipient=facts.recipient,
            actor_is_project_member=facts.actor_is_project_member,
            recipient_is_project_member=facts.recipient_is_project_member,
            actor_can_grant_action=facts.actor_can_grant_action,
        ):
            raise AccessDeniedError

        raise NotImplementedError
