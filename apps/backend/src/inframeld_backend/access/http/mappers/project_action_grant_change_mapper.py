from typing import Literal
from uuid import UUID

from inframeld_backend.access.application.commands.remove_project_action_grant_command import (
    RemoveProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.application.dtos.project_action_grant_change_result_dto import (
    ProjectActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.enums.project_action_grant_change_kind import (
    ProjectActionGrantChangeKind,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.requests.project_action_grant_request import (
    ProjectActionGrantRequest,
)
from inframeld_backend.access.http.responses.project_action_grant_removal_response import (
    ProjectActionGrantRemovalResponse,
)
from inframeld_backend.access.http.responses.project_action_grant_response import (
    ProjectActionGrantResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class ProjectActionGrantChangeMapper:
    @staticmethod
    def _action(value: str) -> ActionId:
        try:
            action = ActionId(value)
        except ValueError as error:
            raise InvalidInputError() from error
        if not ProjectActionEligibilityPolicy.may_use(
            action_id=action, principal_kind=PrincipalKind.HUMAN
        ):
            raise InvalidInputError()
        return action

    @staticmethod
    def set_command(
        project_id: UUID, recipient_id: UUID, action: str, body: ProjectActionGrantRequest
    ) -> SetProjectActionGrantCommand:
        return SetProjectActionGrantCommand(
            ProjectId(project_id),
            PrincipalId(recipient_id),
            ProjectActionGrantChangeMapper._action(action),
            body.can_grant,
            body.expected_access_revision,
        )

    @staticmethod
    def remove_command(
        project_id: UUID, recipient_id: UUID, action: str, revision: int
    ) -> RemoveProjectActionGrantCommand:
        return RemoveProjectActionGrantCommand(
            ProjectId(project_id),
            PrincipalId(recipient_id),
            ProjectActionGrantChangeMapper._action(action),
            revision,
        )

    @staticmethod
    def context(
        command: SetProjectActionGrantCommand | RemoveProjectActionGrantCommand,
        method: Literal[HttpMethod.PUT, HttpMethod.DELETE],
        key: IdempotencyKey,
    ) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            method,
            f"/v1/projects/{command.project_id.value}/grants/{command.recipient_principal_id.value}/{command.action_id.value}",
            key,
        )

    @staticmethod
    def set_response(result: ProjectActionGrantChangeResultDTO) -> ProjectActionGrantResponse:
        if result.change_kind != ProjectActionGrantChangeKind.SET or result.can_grant is None:
            raise RuntimeError("Assignment returned a different original operation result.")
        return ProjectActionGrantResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_id=result.project_id.value,
            recipient_principal_id=result.recipient_principal_id.value,
            action_id=result.action_id.value,
            can_grant=result.can_grant,
            access_revision=result.access_revision,
            changed=result.changed,
        )

    @staticmethod
    def remove_response(
        result: ProjectActionGrantChangeResultDTO,
    ) -> ProjectActionGrantRemovalResponse:
        if (
            result.change_kind != ProjectActionGrantChangeKind.REMOVE
            or result.can_grant is not None
        ):
            raise RuntimeError("Removal returned a different original operation result.")
        return ProjectActionGrantRemovalResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_id=result.project_id.value,
            recipient_principal_id=result.recipient_principal_id.value,
            action_id=result.action_id.value,
            removed=True,
            access_revision=result.access_revision,
            changed=result.changed,
        )
