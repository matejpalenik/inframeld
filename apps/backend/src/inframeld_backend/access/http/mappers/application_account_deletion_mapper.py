from inframeld_backend.access.application.commands.delete_application_account_command import (
    DeleteApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.application_account_deletion_result_dto import (
    ApplicationAccountDeletionResultDTO,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.responses.application_account_deletion_response import (
    ApplicationAccountDeletionResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class ApplicationAccountDeletionMapper:
    @staticmethod
    def command(
        project: ProjectId, application: PrincipalId, revision: int
    ) -> DeleteApplicationAccountCommand:
        return DeleteApplicationAccountCommand(project, application, revision)

    @staticmethod
    def context(
        project: ProjectId, application: PrincipalId, key: IdempotencyKey
    ) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            HttpMethod.DELETE,
            f"/v1/projects/{project.value}/application-accounts/{application.value}",
            key,
        )

    @staticmethod
    def response(
        result: ApplicationAccountDeletionResultDTO,
    ) -> ApplicationAccountDeletionResponse:
        return ApplicationAccountDeletionResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_id=result.original.project_id.value,
            principal_id=result.original.application_principal_id.value,
            access_revision=result.original.access_revision,
            access_blocked=True,
        )
