from inframeld_backend.access.application.dtos.model_connection_credential_dto import (
    ModelConnectionCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_result_dto import (
    ModelConnectionCredentialResultDTO,
)
from inframeld_backend.access.http.responses.model_connection_credential_details_response import (
    ModelConnectionCredentialDetailsResponse,
)
from inframeld_backend.access.http.responses.model_connection_credential_result_response import (
    ModelConnectionCredentialResultResponse,
)


class ModelConnectionCredentialMapper:
    @staticmethod
    def details(
        credential: ModelConnectionCredentialDTO,
    ) -> ModelConnectionCredentialDetailsResponse:
        return ModelConnectionCredentialDetailsResponse(
            project_id=credential.project_id.value,
            model_connection_id=credential.connection_id.value,
            credential_id=credential.credential_id,
            revision=credential.revision,
            present=credential.present,
            changed_at=credential.changed_at,
        )

    @staticmethod
    def result(
        result: ModelConnectionCredentialResultDTO,
    ) -> ModelConnectionCredentialResultResponse:
        return ModelConnectionCredentialResultResponse(
            credential=ModelConnectionCredentialMapper.details(result.credential),
            changed=result.changed,
            replayed=not result.operation.created,
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
        )
