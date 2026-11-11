from uuid import UUID

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.access.application.dtos.project_upload_default_change_result_dto import (
    ProjectUploadDefaultChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_dto import (
    ProjectUploadDefaultDTO,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.access.http.requests.project_upload_default_request import (
    ProjectUploadDefaultRequest,
)
from inframeld_backend.access.http.responses.project_upload_default_change_response import (
    ProjectUploadDefaultChangeResponse,
)
from inframeld_backend.access.http.responses.project_upload_default_response import (
    ProjectUploadDefaultResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class ProjectUploadDefaultMapper:
    @staticmethod
    def command(
        project_id: UUID, request: ProjectUploadDefaultRequest
    ) -> SetProjectUploadDefaultCommand:
        return SetProjectUploadDefaultCommand(
            ProjectId(project_id),
            UploadAudience(tuple(AccessGroupId(group) for group in request.group_ids)),
            request.expected_access_revision,
        )

    @staticmethod
    def context(project_id: UUID, key: IdempotencyKey) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            HttpMethod.PUT, f"/v1/projects/{project_id}/upload-defaults", key
        )

    @staticmethod
    def current(result: ProjectUploadDefaultDTO) -> ProjectUploadDefaultResponse:
        return ProjectUploadDefaultResponse(
            project_id=result.project_id.value,
            access_revision=result.access_revision,
            group_ids=None
            if result.audience is None
            else [group.value for group in result.audience.group_ids],
        )

    @staticmethod
    def changed(result: ProjectUploadDefaultChangeResultDTO) -> ProjectUploadDefaultChangeResponse:
        if result.default.audience is None:
            raise RuntimeError(
                "A completed upload-default replacement must retain its resulting audience."
            )
        return ProjectUploadDefaultChangeResponse(
            project_id=result.default.project_id.value,
            access_revision=result.default.access_revision,
            group_ids=[group.value for group in result.default.audience.group_ids],
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
        )
