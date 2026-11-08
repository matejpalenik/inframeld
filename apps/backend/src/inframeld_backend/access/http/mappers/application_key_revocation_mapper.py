from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.application_key_revocation_result_dto import (
    ApplicationKeyRevocationResultDTO,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.mappers.application_account_mapper import (
    ApplicationAccountMapper,
)
from inframeld_backend.access.http.requests.application_key_revocation_request import (
    ApplicationKeyRevocationRequest,
)
from inframeld_backend.access.http.responses.application_key_revocation_response import (
    ApplicationKeyRevocationResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class ApplicationKeyRevocationMapper:
    @staticmethod
    def command(
        project: ProjectId,
        application: PrincipalId,
        key: ApplicationKeyId,
        body: ApplicationKeyRevocationRequest,
    ) -> RevokeApplicationKeyCommand:
        return RevokeApplicationKeyCommand(project, application, key, body.expected_access_revision)

    @staticmethod
    def context(
        project: ProjectId,
        application: PrincipalId,
        key: ApplicationKeyId,
        original: IdempotencyKey,
    ) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            HttpMethod.POST,
            f"/v1/projects/{project.value}/application-accounts/{application.value}/keys/{key.value}/revoke",
            original,
        )

    @staticmethod
    def response(result: ApplicationKeyRevocationResultDTO) -> ApplicationKeyRevocationResponse:
        return ApplicationKeyRevocationResponse(
            operation_id=result.operation.operation_id.value,
            access_revision=result.original.access_revision,
            idempotency_expires_at=result.operation.expires_at,
            metadata=ApplicationAccountMapper.key(result.original.metadata),
        )
