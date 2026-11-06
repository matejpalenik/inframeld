from typing import Literal
from uuid import UUID

from inframeld_backend.access.application.commands.remove_application_account_action_grant_command import (
    RemoveApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_application_account_action_grant_command import (
    SetApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.dtos.application_account_action_grant_change_result_dto import (
    ApplicationAccountActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.application_account_action_grants_page_dto import (
    ApplicationAccountActionGrantsPageDTO,
)
from inframeld_backend.access.application.queries.list_application_account_action_grants_query import (
    ListApplicationAccountActionGrantsQuery,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.application_account_grant_policy import (
    ApplicationAccountGrantPolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.requests.application_account_action_grant_request import (
    ApplicationAccountActionGrantRequest,
)
from inframeld_backend.access.http.responses.application_account_action_grant_item_response import (
    ApplicationAccountActionGrantItemResponse,
)
from inframeld_backend.access.http.responses.application_account_action_grant_removal_response import (
    ApplicationAccountActionGrantRemovalResponse,
)
from inframeld_backend.access.http.responses.application_account_action_grant_response import (
    ApplicationAccountActionGrantResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery
from inframeld_backend.shared.http.responses.page_response import PageResponse


class ApplicationAccountActionGrantMapper:
    @staticmethod
    def _action(value: str) -> ActionId:
        try:
            action = ActionId(value)
        except ValueError as error:
            raise InvalidInputError("The action identifier is invalid.") from error
        if not ApplicationAccountGrantPolicy.supports_recipient(
            action_id=action, kind=PrincipalKind.HUMAN
        ):
            raise InvalidInputError("The action is not supported for this target.")
        return action

    @staticmethod
    def query(
        *,
        project_id: UUID,
        application_principal_id: UUID,
        action_id: str,
        pagination: PaginationQuery,
    ) -> ListApplicationAccountActionGrantsQuery:
        return ListApplicationAccountActionGrantsQuery(
            project_id=ProjectId(project_id),
            application_principal_id=PrincipalId(application_principal_id),
            action_id=ApplicationAccountActionGrantMapper._action(action_id),
            limit=pagination.limit,
            cursor=pagination.cursor,
        )

    @staticmethod
    def set_command(
        *,
        project_id: UUID,
        application_principal_id: UUID,
        recipient_principal_id: UUID,
        action_id: str,
        body: ApplicationAccountActionGrantRequest,
    ) -> SetApplicationAccountActionGrantCommand:
        return SetApplicationAccountActionGrantCommand(
            project_id=ProjectId(project_id),
            application_principal_id=PrincipalId(application_principal_id),
            recipient_principal_id=PrincipalId(recipient_principal_id),
            action_id=ApplicationAccountActionGrantMapper._action(action_id),
            can_grant=body.can_grant,
            expected_access_revision=body.expected_access_revision,
        )

    @staticmethod
    def remove_command(
        *,
        project_id: UUID,
        application_principal_id: UUID,
        recipient_principal_id: UUID,
        action_id: str,
        expected_access_revision: int,
    ) -> RemoveApplicationAccountActionGrantCommand:
        return RemoveApplicationAccountActionGrantCommand(
            project_id=ProjectId(project_id),
            application_principal_id=PrincipalId(application_principal_id),
            recipient_principal_id=PrincipalId(recipient_principal_id),
            action_id=ApplicationAccountActionGrantMapper._action(action_id),
            expected_access_revision=expected_access_revision,
        )

    @staticmethod
    def context(
        *,
        command: SetApplicationAccountActionGrantCommand
        | RemoveApplicationAccountActionGrantCommand,
        method: Literal[HttpMethod.PUT, HttpMethod.DELETE],
        key: IdempotencyKey,
    ) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            method=method,
            requested_route=f"/v1/projects/{command.project_id.value}/application-accounts/{command.application_principal_id.value}/grants/{command.recipient_principal_id.value}/{command.action_id.value}",
            key=key,
        )

    @staticmethod
    def set_response(
        result: ApplicationAccountActionGrantChangeResultDTO,
    ) -> ApplicationAccountActionGrantResponse:
        if result.method != HttpMethod.PUT or result.can_grant is None:
            raise RuntimeError("Assignment returned a different original operation result.")
        return ApplicationAccountActionGrantResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_id=result.project_id.value,
            application_principal_id=result.application_principal_id.value,
            recipient_principal_id=result.recipient_principal_id.value,
            action_id=result.action_id.value,
            can_grant=result.can_grant,
            access_revision=result.access_revision,
            changed=result.changed,
        )

    @staticmethod
    def remove_response(
        result: ApplicationAccountActionGrantChangeResultDTO,
    ) -> ApplicationAccountActionGrantRemovalResponse:
        if result.method != HttpMethod.DELETE or result.can_grant is not None:
            raise RuntimeError("Removal returned a different original operation result.")
        return ApplicationAccountActionGrantRemovalResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_id=result.project_id.value,
            application_principal_id=result.application_principal_id.value,
            recipient_principal_id=result.recipient_principal_id.value,
            action_id=result.action_id.value,
            removed=True,
            access_revision=result.access_revision,
            changed=result.changed,
        )

    @staticmethod
    def page_response(
        page: ApplicationAccountActionGrantsPageDTO,
    ) -> PageResponse[ApplicationAccountActionGrantItemResponse]:
        return PageResponse[ApplicationAccountActionGrantItemResponse](
            items=[
                ApplicationAccountActionGrantItemResponse(
                    project_id=page.project_id.value,
                    application_principal_id=page.application_principal_id.value,
                    recipient_principal_id=item.recipient_principal_id.value,
                    action_id=item.action_id.value,
                    can_grant=item.can_grant,
                )
                for item in page.items
            ],
            next_cursor=page.next_cursor,
        )
