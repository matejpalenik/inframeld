from inframeld_backend.access.application.dtos.project_deletion_result_dto import (
    ProjectDeletionResultDTO,
)
from inframeld_backend.access.http.responses.project_deletion_admission_response import (
    ProjectDeletionAdmissionResponse,
)


class ProjectDeletionMapper:
    @staticmethod
    def admission(result: ProjectDeletionResultDTO) -> ProjectDeletionAdmissionResponse:
        return ProjectDeletionAdmissionResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_id=result.project_id.value,
            access_revision=result.access_revision,
            admission_confirmed=True,
            access_blocked=True,
        )
