from uuid import UUID

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.requests.project_use_only_grant_request import (
    ProjectUseOnlyGrantRequest,
)
from inframeld_backend.access.http.responses.project_use_only_grant_response import (
    ProjectUseOnlyGrantResponse,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class ProjectUseOnlyGrantMapper:
    """Convert the published grant contract without performing authorization or I/O."""

    @staticmethod
    def to_command(
        *, project_id: UUID, request: ProjectUseOnlyGrantRequest
    ) -> AssignProjectUseOnlyGrantCommand:
        return AssignProjectUseOnlyGrantCommand(
            project_id=ProjectId(project_id),
            recipient_principal_id=PrincipalId(request.recipient_principal_id),
            action_id=ActionId(request.action_id),
            expected_access_revision=request.expected_access_revision,
        )

    @staticmethod
    def to_operation_context(key: IdempotencyKey) -> OperationAdmissionContextDTO:
        return OperationAdmissionContextDTO(
            method="POST", requested_route="/v1/projects/{project_id}/grants", key=key
        )

    @staticmethod
    def to_response(
        *, command: AssignProjectUseOnlyGrantCommand, result: CompletedSynchronousOperationDTO
    ) -> ProjectUseOnlyGrantResponse:
        action = command.action_id.value
        if action != "create-access-groups":
            raise ValueError("Unsupported project grant action.")
        return ProjectUseOnlyGrantResponse(
            operation_id=result.operation_id.value,
            project_id=command.project_id.value,
            recipient_principal_id=command.recipient_principal_id.value,
            action_id=action,
            access_revision=command.expected_access_revision + 1,
            idempotency_expires_at=result.expires_at,
        )
