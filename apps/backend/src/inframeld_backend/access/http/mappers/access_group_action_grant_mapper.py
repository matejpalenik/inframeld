from typing import Literal
from uuid import UUID

from inframeld_backend.access.application.commands.remove_access_group_action_grant_command import (
    RemoveAccessGroupActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_access_group_action_grant_command import (
    SetAccessGroupActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_group_action_grant_change_result_dto import (
    AccessGroupActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_action_grants_page_dto import (
    AccessGroupActionGrantsPageDTO,
)
from inframeld_backend.access.application.queries.list_access_group_action_grants_query import (
    ListAccessGroupActionGrantsQuery,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.access_group_grant_policy import (
    AccessGroupGrantPolicy,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.requests.access_group_action_grant_request import (
    AccessGroupActionGrantRequest,
)
from inframeld_backend.access.http.responses.access_group_action_grant_item_response import (
    AccessGroupActionGrantItemResponse,
)
from inframeld_backend.access.http.responses.access_group_action_grant_removal_response import (
    AccessGroupActionGrantRemovalResponse,
)
from inframeld_backend.access.http.responses.access_group_action_grant_response import (
    AccessGroupActionGrantResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery
from inframeld_backend.shared.http.responses.page_response import PageResponse


class AccessGroupActionGrantMapper:
    @staticmethod
    def _action(value: str) -> ActionId:
        try:
            action = ActionId(value)
        except ValueError as error:
            raise InvalidInputError("The action identifier is invalid.") from error
        if not AccessGroupGrantPolicy.supports_recipient(
            action_id=action, kind=PrincipalKind.HUMAN, can_grant=False
        ):
            raise InvalidInputError("The action is not supported for this target.")
        return action

    @staticmethod
    def query(
        *, project_id: UUID, access_group_id: UUID, action_id: str, pagination: PaginationQuery
    ) -> ListAccessGroupActionGrantsQuery:
        return ListAccessGroupActionGrantsQuery(
            project_id=ProjectId(project_id),
            group_id=AccessGroupId(access_group_id),
            action_id=AccessGroupActionGrantMapper._action(action_id),
            limit=pagination.limit,
            cursor=pagination.cursor,
        )

    @staticmethod
    def set_command(
        *,
        project_id: UUID,
        access_group_id: UUID,
        recipient_principal_id: UUID,
        action_id: str,
        body: AccessGroupActionGrantRequest,
    ) -> SetAccessGroupActionGrantCommand:
        return SetAccessGroupActionGrantCommand(
            project_id=ProjectId(project_id),
            group_id=AccessGroupId(access_group_id),
            recipient_principal_id=PrincipalId(recipient_principal_id),
            action_id=AccessGroupActionGrantMapper._action(action_id),
            can_grant=body.can_grant,
            expected_access_revision=body.expected_access_revision,
        )

    @staticmethod
    def remove_command(
        *,
        project_id: UUID,
        access_group_id: UUID,
        recipient_principal_id: UUID,
        action_id: str,
        expected_access_revision: int,
    ) -> RemoveAccessGroupActionGrantCommand:
        return RemoveAccessGroupActionGrantCommand(
            project_id=ProjectId(project_id),
            group_id=AccessGroupId(access_group_id),
            recipient_principal_id=PrincipalId(recipient_principal_id),
            action_id=AccessGroupActionGrantMapper._action(action_id),
            expected_access_revision=expected_access_revision,
        )

    @staticmethod
    def context(
        *,
        command: SetAccessGroupActionGrantCommand | RemoveAccessGroupActionGrantCommand,
        method: Literal[HttpMethod.PUT, HttpMethod.DELETE],
        key: IdempotencyKey,
    ) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            method=method,
            requested_route=f"/v1/projects/{command.project_id.value}/access-groups/{command.group_id.value}/grants/{command.recipient_principal_id.value}/{command.action_id.value}",
            key=key,
        )

    @staticmethod
    def set_response(
        result: AccessGroupActionGrantChangeResultDTO,
    ) -> AccessGroupActionGrantResponse:
        if result.method != HttpMethod.PUT or result.can_grant is None:
            raise RuntimeError("Assignment returned a different original operation result.")
        return AccessGroupActionGrantResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_id=result.project_id.value,
            access_group_id=result.group_id.value,
            recipient_principal_id=result.recipient_principal_id.value,
            action_id=result.action_id.value,
            can_grant=result.can_grant,
            access_revision=result.access_revision,
            changed=result.changed,
        )

    @staticmethod
    def remove_response(
        result: AccessGroupActionGrantChangeResultDTO,
    ) -> AccessGroupActionGrantRemovalResponse:
        if result.method != HttpMethod.DELETE or result.can_grant is not None:
            raise RuntimeError("Removal returned a different original operation result.")
        return AccessGroupActionGrantRemovalResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_id=result.project_id.value,
            access_group_id=result.group_id.value,
            recipient_principal_id=result.recipient_principal_id.value,
            action_id=result.action_id.value,
            removed=True,
            access_revision=result.access_revision,
            changed=result.changed,
        )

    @staticmethod
    def page_response(
        page: AccessGroupActionGrantsPageDTO,
    ) -> PageResponse[AccessGroupActionGrantItemResponse]:
        return PageResponse[AccessGroupActionGrantItemResponse](
            items=[
                AccessGroupActionGrantItemResponse(
                    project_id=page.project_id.value,
                    access_group_id=page.group_id.value,
                    recipient_principal_id=item.recipient_principal_id.value,
                    action_id=item.action_id.value,
                    can_grant=item.can_grant,
                )
                for item in page.items
            ],
            next_cursor=page.next_cursor,
        )
