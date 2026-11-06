from typing import Literal
from uuid import UUID

from inframeld_backend.access.application.commands.remove_organization_action_grant_command import (
    RemoveOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_organization_action_grant_command import (
    SetOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.dtos.organization_action_grant_change_result_dto import (
    OrganizationActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grants_page_dto import (
    OrganizationActionGrantsPageDTO,
)
from inframeld_backend.access.application.queries.list_organization_action_grants_query import (
    ListOrganizationActionGrantsQuery,
)
from inframeld_backend.access.domain.policies.organization_grant_policy import (
    OrganizationGrantPolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.requests.organization_action_grant_request import (
    OrganizationActionGrantRequest,
)
from inframeld_backend.access.http.responses.organization_action_grant_item_response import (
    OrganizationActionGrantItemResponse,
)
from inframeld_backend.access.http.responses.organization_action_grant_removal_response import (
    OrganizationActionGrantRemovalResponse,
)
from inframeld_backend.access.http.responses.organization_action_grant_response import (
    OrganizationActionGrantResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery
from inframeld_backend.shared.http.responses.page_response import PageResponse


class OrganizationActionGrantMapper:
    @staticmethod
    def _action(value: str) -> ActionId:
        try:
            action = ActionId(value)
        except ValueError as error:
            raise InvalidInputError("The action identifier is invalid.") from error
        if not OrganizationGrantPolicy.supports_action(action):
            raise InvalidInputError("The action is not supported for this target.")
        return action

    @staticmethod
    def query(
        *, organization_id: UUID, action_id: str, pagination: PaginationQuery
    ) -> ListOrganizationActionGrantsQuery:
        return ListOrganizationActionGrantsQuery(
            organization_id=OrganizationId(organization_id),
            action_id=OrganizationActionGrantMapper._action(action_id),
            limit=pagination.limit,
            cursor=pagination.cursor,
        )

    @staticmethod
    def set_command(
        *,
        organization_id: UUID,
        recipient_principal_id: UUID,
        action_id: str,
        body: OrganizationActionGrantRequest,
    ) -> SetOrganizationActionGrantCommand:
        return SetOrganizationActionGrantCommand(
            organization_id=OrganizationId(organization_id),
            recipient_principal_id=PrincipalId(recipient_principal_id),
            action_id=OrganizationActionGrantMapper._action(action_id),
            can_grant=body.can_grant,
            expected_access_revision=body.expected_access_revision,
        )

    @staticmethod
    def remove_command(
        *,
        organization_id: UUID,
        recipient_principal_id: UUID,
        action_id: str,
        expected_access_revision: int,
    ) -> RemoveOrganizationActionGrantCommand:
        return RemoveOrganizationActionGrantCommand(
            organization_id=OrganizationId(organization_id),
            recipient_principal_id=PrincipalId(recipient_principal_id),
            action_id=OrganizationActionGrantMapper._action(action_id),
            expected_access_revision=expected_access_revision,
        )

    @staticmethod
    def context(
        *,
        command: SetOrganizationActionGrantCommand | RemoveOrganizationActionGrantCommand,
        method: Literal[HttpMethod.PUT, HttpMethod.DELETE],
        key: IdempotencyKey,
    ) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            method=method,
            requested_route=f"/v1/organizations/{command.organization_id.value}/grants/{command.recipient_principal_id.value}/{command.action_id.value}",
            key=key,
        )

    @staticmethod
    def set_response(
        result: OrganizationActionGrantChangeResultDTO,
    ) -> OrganizationActionGrantResponse:
        if result.method != HttpMethod.PUT or result.can_grant is None:
            raise RuntimeError("Assignment returned a different original operation result.")
        return OrganizationActionGrantResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            organization_id=result.organization_id.value,
            recipient_principal_id=result.recipient_principal_id.value,
            action_id=result.action_id.value,
            can_grant=result.can_grant,
            access_revision=result.access_revision,
            changed=result.changed,
        )

    @staticmethod
    def remove_response(
        result: OrganizationActionGrantChangeResultDTO,
    ) -> OrganizationActionGrantRemovalResponse:
        if result.method != HttpMethod.DELETE or result.can_grant is not None:
            raise RuntimeError("Removal returned a different original operation result.")
        return OrganizationActionGrantRemovalResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            organization_id=result.organization_id.value,
            recipient_principal_id=result.recipient_principal_id.value,
            action_id=result.action_id.value,
            removed=True,
            access_revision=result.access_revision,
            changed=result.changed,
        )

    @staticmethod
    def page_response(
        page: OrganizationActionGrantsPageDTO,
    ) -> PageResponse[OrganizationActionGrantItemResponse]:
        return PageResponse[OrganizationActionGrantItemResponse](
            items=[
                OrganizationActionGrantItemResponse(
                    organization_id=page.organization_id.value,
                    recipient_principal_id=item.recipient_principal_id.value,
                    action_id=item.action_id.value,
                    can_grant=item.can_grant,
                )
                for item in page.items
            ],
            next_cursor=page.next_cursor,
        )
