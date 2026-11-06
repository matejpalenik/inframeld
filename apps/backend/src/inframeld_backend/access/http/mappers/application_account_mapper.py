from inframeld_backend.access.application.commands.create_application_account_command import (
    CreateApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.application_account_creation_result_dto import (
    ApplicationAccountCreationResultDTO,
)
from inframeld_backend.access.application.dtos.application_account_metadata_dto import (
    ApplicationAccountMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_keys_page_dto import (
    ApplicationKeysPageDTO,
)
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.application_key_prefix import ApplicationKeyPrefix
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.enums.grant_target_kind import GrantTargetKind
from inframeld_backend.access.http.requests.application_account_creation_request import (
    ApplicationAccountCreationRequest,
)
from inframeld_backend.access.http.responses.application_account_creation_response import (
    ApplicationAccountCreationResponse,
)
from inframeld_backend.access.http.responses.application_account_grant_target_response import (
    ApplicationAccountGrantTargetResponse,
)
from inframeld_backend.access.http.responses.application_account_metadata_response import (
    ApplicationAccountMetadataResponse,
)
from inframeld_backend.access.http.responses.application_key_metadata_response import (
    ApplicationKeyMetadataResponse,
)
from inframeld_backend.access.http.responses.initial_application_account_grant_response import (
    InitialApplicationAccountGrantResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.http.responses.page_response import PageResponse


class ApplicationAccountMapper:
    @staticmethod
    def command(
        project_id: ProjectId, body: ApplicationAccountCreationRequest
    ) -> CreateApplicationAccountCommand:
        return CreateApplicationAccountCommand(
            project_id,
            body.expected_access_revision,
            ResourceName(body.name),
            SubmittedDisplayName(body.display_name),
        )

    @staticmethod
    def context(project_id: ProjectId, key: IdempotencyKey) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            HttpMethod.POST, f"/v1/projects/{project_id.value}/application-accounts", key
        )

    @staticmethod
    def creation(result: ApplicationAccountCreationResultDTO) -> ApplicationAccountCreationResponse:
        account = result.account
        target = ApplicationAccountGrantTargetResponse(
            kind=GrantTargetKind.APPLICATION_ACCOUNT,
            project_id=account.project_id.value,
            application_principal_id=account.principal_id.value,
        )
        return ApplicationAccountCreationResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_id=account.project_id.value,
            principal_id=account.principal_id.value,
            name=account.name.value,
            display_name=account.display_name,
            access_revision=account.access_revision,
            initial_grants=tuple(
                InitialApplicationAccountGrantResponse(
                    target=target, action_id=ApplicationAccountAction(action.value), can_grant=True
                )
                for action in account.initial_actions
            ),
        )

    @staticmethod
    def metadata(account: ApplicationAccountMetadataDTO) -> ApplicationAccountMetadataResponse:
        return ApplicationAccountMetadataResponse(
            project_id=account.project_id.value,
            principal_id=account.principal_id.value,
            name=account.name.value if account.name is not None else None,
            display_name=account.display_name,
            status=account.status,
            created_at=account.created_at,
            access_revision=account.access_revision,
        )

    @staticmethod
    def key(key: ApplicationKeyMetadataDTO) -> ApplicationKeyMetadataResponse:
        return ApplicationKeyMetadataResponse(
            key_id=key.key_id.value,
            application_principal_id=key.application_principal_id.value,
            project_id=key.project_id.value,
            prefix=ApplicationKeyPrefix.APPLICATION,
            allowed_adapters=key.allowed_adapters,
            created_at=key.created_at,
            expires_at=key.expires_at,
            revoked_at=key.revoked_at,
        )

    @staticmethod
    def page(page: ApplicationKeysPageDTO) -> PageResponse[ApplicationKeyMetadataResponse]:
        return PageResponse(
            items=[ApplicationAccountMapper.key(key) for key in page.items],
            next_cursor=page.next_cursor,
        )
