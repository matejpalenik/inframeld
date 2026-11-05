from inframeld_backend.access.application.commands.create_project_command import (
    CreateProjectCommand,
)
from inframeld_backend.access.application.dtos.project_creation_result_dto import (
    ProjectCreationResultDTO,
)
from inframeld_backend.access.domain.enums.project_departure_target_kind import (
    ProjectDepartureTargetKind,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.http.requests.project_creation_request import ProjectCreationRequest
from inframeld_backend.access.http.responses.initial_project_grant_response import (
    InitialProjectGrantResponse,
)
from inframeld_backend.access.http.responses.project_creation_response import (
    ProjectCreationResponse,
)
from inframeld_backend.access.http.responses.project_grant_target_response import (
    ProjectGrantTargetResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


class ProjectCreationMapper:
    @staticmethod
    def command(body: ProjectCreationRequest) -> CreateProjectCommand:
        return CreateProjectCommand(
            OrganizationId(body.organization_id),
            body.expected_access_revision,
            ResourceName(body.name),
            SubmittedDisplayName(body.display_name),
        )

    @staticmethod
    def context(key: IdempotencyKey) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(HttpMethod.POST, "/v1/projects", key)

    @staticmethod
    def response(result: ProjectCreationResultDTO) -> ProjectCreationResponse:
        project = result.project
        target = ProjectGrantTargetResponse(
            kind=ProjectDepartureTargetKind.PROJECT, project_id=project.project_id.value
        )
        return ProjectCreationResponse.model_validate(
            {
                "operation_id": result.operation.operation_id.value,
                "idempotency_expires_at": result.operation.expires_at,
                "organization_id": project.organization_id.value,
                "project_id": project.project_id.value,
                "name": project.name.value,
                "display_name": project.display_name,
                "access_revision": project.access_revision,
                "metadata_revision": project.metadata_revision,
                "initial_grants": tuple(
                    InitialProjectGrantResponse.model_validate(
                        {"target": target, "action_id": action.value, "can_grant": True}
                    )
                    for action in project.initial_actions
                ),
            }
        )
