from uuid import UUID

from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.knowledge.application.commands.upload_document_command import (
    UploadDocumentCommand,
)
from inframeld_backend.knowledge.application.dtos.document_upload_result_dto import (
    DocumentUploadResultDTO,
)
from inframeld_backend.knowledge.http.responses.document_upload_response import (
    DocumentUploadResponse,
)
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_id import RequestId


class DocumentUploadMapper:
    @staticmethod
    def command(
        project_id: UUID,
        group_ids: list[UUID],
        filename: str,
        key: IdempotencyKey,
        request_id: RequestId,
    ) -> UploadDocumentCommand:
        try:
            audience = UploadAudience(tuple(AccessGroupId(group) for group in group_ids))
        except ValueError as error:
            raise InvalidInputError("The upload requires a distinct explicit audience.") from error
        return UploadDocumentCommand(ProjectId(project_id), audience, filename, key, request_id)

    @staticmethod
    def response(result: DocumentUploadResultDTO) -> DocumentUploadResponse:
        return DocumentUploadResponse(
            operation_id=result.operation_id.value,
            project_id=result.project_id.value,
            document_id=result.document_id.value,
            version_id=result.version_id.value,
            idempotency_expires_at=result.idempotency_expires_at,
        )
