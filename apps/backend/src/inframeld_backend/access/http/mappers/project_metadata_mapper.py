from dataclasses import replace
from uuid import UUID

from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.application.dtos.project_metadata_change_result_dto import (
    ProjectMetadataChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.access.application.errors.retired_project_name_error import (
    RetiredProjectNameError,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.requests.project_metadata_update_request import (
    ProjectMetadataUpdateRequest,
)
from inframeld_backend.access.http.responses.project_metadata_change_response import (
    ProjectMetadataChangeResponse,
)
from inframeld_backend.access.http.responses.project_metadata_response import (
    ProjectMetadataResponse,
)
from inframeld_backend.access.http.responses.project_name_resolution_response import (
    ProjectNameResolutionResponse,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.http.definitions.problem_catalogue import RESOURCE_NOT_FOUND_PROBLEM
from inframeld_backend.shared.http.definitions.problem_definition import ProblemDefinition


class ProjectMetadataMapper:
    @staticmethod
    def retired(error: RetiredProjectNameError) -> ProblemDefinition:
        identity = str(error.project_id.value)
        detail = (
            f"This Name is retired. Project {identity} now uses Name '{error.current_name.value}'. "
            "Inspect or select it explicitly by its permanent ID."
            if error.current_name is not None
            else f"The original Project is {identity}. It has no current Name. Inspect it by permanent ID."
        )
        return replace(RESOURCE_NOT_FOUND_PROBLEM, detail=detail)

    @staticmethod
    def to_command(
        project_id: UUID, request: ProjectMetadataUpdateRequest
    ) -> UpdateProjectMetadataCommand:
        return UpdateProjectMetadataCommand(
            ProjectId(project_id),
            request.expected_metadata_revision,
            None if request.name is None else ResourceName(request.name),
            None if request.display_name is None else SubmittedDisplayName(request.display_name),
        )

    @staticmethod
    def context(key: IdempotencyKey) -> OperationAdmissionContextDTO:
        return OperationAdmissionContextDTO("PATCH", "/v1/projects/{project_id}/metadata", key)

    @staticmethod
    def metadata(result: ProjectMetadataDTO) -> ProjectMetadataResponse:
        return ProjectMetadataResponse(
            project_id=result.project_id.value,
            organization_id=result.organization_id.value,
            name=None if result.name is None else result.name.value,
            display_name=result.display_name,
            metadata_revision=result.metadata_revision,
        )

    @staticmethod
    def changed(result: ProjectMetadataChangeResultDTO) -> ProjectMetadataChangeResponse:
        metadata = result.metadata
        return ProjectMetadataChangeResponse(
            project_id=metadata.project_id.value,
            organization_id=metadata.organization_id.value,
            name=None if metadata.name is None else metadata.name.value,
            display_name=metadata.display_name,
            metadata_revision=metadata.metadata_revision,
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
        )

    @staticmethod
    def resolved(result: ProjectMetadataDTO) -> ProjectNameResolutionResponse:
        return ProjectNameResolutionResponse(
            project_id=result.project_id.value,
            organization_id=result.organization_id.value,
            name=None if result.name is None else result.name.value,
            display_name=result.display_name,
            metadata_revision=result.metadata_revision,
        )
