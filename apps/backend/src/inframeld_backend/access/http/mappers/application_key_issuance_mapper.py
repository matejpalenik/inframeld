from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.application_key_issue_result_dto import (
    ApplicationKeyIssueResultDTO,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.mappers.application_account_mapper import (
    ApplicationAccountMapper,
)
from inframeld_backend.access.http.requests.application_key_issue_request import (
    ApplicationKeyIssueRequest,
)
from inframeld_backend.access.http.responses.application_key_first_delivery_response import (
    ApplicationKeyFirstDeliveryResponse,
)
from inframeld_backend.access.http.responses.application_key_issuance_replay_response import (
    ApplicationKeyIssuanceReplayResponse,
)
from inframeld_backend.access.http.responses.application_key_issue_response import (
    ApplicationKeyIssueResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class ApplicationKeyIssuanceMapper:
    @staticmethod
    def command(
        project: ProjectId, application: PrincipalId, body: ApplicationKeyIssueRequest
    ) -> IssueApplicationKeyCommand:
        return IssueApplicationKeyCommand(
            project,
            application,
            tuple(body.allowed_adapters),
            body.expected_access_revision,
            body.expires_in_seconds,
        )

    @staticmethod
    def context(
        project: ProjectId, application: PrincipalId, key: IdempotencyKey
    ) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            HttpMethod.POST,
            f"/v1/projects/{project.value}/application-accounts/{application.value}/keys",
            key,
        )

    @staticmethod
    def response(result: ApplicationKeyIssueResultDTO) -> ApplicationKeyIssueResponse:
        metadata = ApplicationAccountMapper.key(result.original.metadata)
        if result.credential is not None:
            if not result.operation.created:
                raise RuntimeError("A replay cannot deliver an application-key secret.")
            return ApplicationKeyIssueResponse(
                ApplicationKeyFirstDeliveryResponse(
                    operation_id=result.operation.operation_id.value,
                    access_revision=result.original.access_revision,
                    idempotency_expires_at=result.operation.expires_at,
                    metadata=metadata,
                    secretAvailable=True,
                    key=result.credential.value,
                )
            )
        if result.operation.created:
            raise RuntimeError("A first issuance cannot omit its credential delivery.")
        return ApplicationKeyIssueResponse(
            ApplicationKeyIssuanceReplayResponse(
                operation_id=result.operation.operation_id.value,
                access_revision=result.original.access_revision,
                idempotency_expires_at=result.operation.expires_at,
                metadata=metadata,
                secretAvailable=False,
            )
        )
