from inframeld_backend.access.application.commands.create_model_connection_command import (
    CreateModelConnectionCommand,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.model_connection_creation_dto import (
    ModelConnectionCreationDTO,
)
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.requests.model_connection_creation_request import (
    ModelConnectionCreationRequest,
)
from inframeld_backend.access.http.responses.model_connection_creation_response import (
    InitialModelConnectionGrantResponse,
    ModelConnectionCreationResponse,
)
from inframeld_backend.access.http.responses.model_connection_grant_target_response import (
    ModelConnectionGrantTargetResponse,
)
from inframeld_backend.access.http.responses.model_connection_response import (
    ModelConnectionAccessResponse,
    ModelConnectionCredentialResponse,
    ModelConnectionResponse,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


class ModelConnectionMapper:
    @staticmethod
    def command(
        project_id: ProjectId, body: ModelConnectionCreationRequest
    ) -> CreateModelConnectionCommand:
        return CreateModelConnectionCommand(
            project_id,
            ResourceName(body.name),
            SubmittedDisplayName(body.display_name),
            ModelConnectionAccessDTO(
                body.access.provider,
                body.access.base_url,
                body.access.api_version,
                body.access.authentication,
            ),
        )

    @staticmethod
    def connection(item: ModelConnectionDTO) -> ModelConnectionResponse:
        return ModelConnectionResponse(
            project_id=item.project_id.value,
            model_connection_id=item.connection_id.value,
            name=item.name.value,
            display_name=item.display_name,
            access=ModelConnectionAccessResponse(
                provider=item.access.provider,
                base_url=item.access.base_url,
                api_version=item.access.api_version,
                authentication=item.access.authentication,
            ),
            connection_access_revision=item.connection_access_revision,
            credential=ModelConnectionCredentialResponse(
                present=item.credential_present,
                revision=item.credential_revision,
            ),
        )

    @staticmethod
    def creation(result: ModelConnectionCreationDTO) -> ModelConnectionCreationResponse:
        target = ModelConnectionGrantTargetResponse(
            kind="model-connection",
            model_connection_id=result.connection.connection_id.value,
        )
        return ModelConnectionCreationResponse(
            connection=ModelConnectionMapper.connection(result.connection),
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_access_revision=result.project_access_revision,
            initial_grants=tuple(
                InitialModelConnectionGrantResponse(target=target, action_id=action, can_grant=True)
                for action in result.initial_actions
            ),
        )
