from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from inframeld_backend.access.application.commands.change_model_connection_grant_command import (
    ChangeModelConnectionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_grant_result_dto import (
    ModelConnectionGrantResultDTO,
)
from inframeld_backend.access.application.protocols.model_connection_grant_changer import (
    ModelConnectionGrantChanger,
)
from inframeld_backend.access.application.protocols.model_connection_grants_reader import (
    ModelConnectionGrantsReader,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.model_connection_action_grant_request import (
    ModelConnectionActionGrantRequest,
)
from inframeld_backend.access.http.responses.model_connection_action_grant_item_response import (
    ModelConnectionActionGrantItemResponse,
)
from inframeld_backend.access.http.responses.model_connection_action_grant_removal_response import (
    ModelConnectionActionGrantRemovalResponse,
)
from inframeld_backend.access.http.responses.model_connection_action_grant_response import (
    ModelConnectionActionGrantResponse,
)
from inframeld_backend.access.http.routes.action_grant_route import ActionGrantRoute
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    CONFLICT_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INVALID_INPUT_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    STALE_REVISION_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.dependencies.idempotency_key_dependency import (
    IdempotencyKeyDependency,
)
from inframeld_backend.shared.http.mappers.problem_mapper import for_http_status
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery
from inframeld_backend.shared.http.responses.page_response import PageResponse

_GRANTS = "/v1/model-connections/{model_connection_id}/grants"
_ASSIGNMENT = _GRANTS + "/{recipient_principal_id}/{action_id}"


def create_model_connection_grant_router(
    authenticate: ProductAccessDependency,
    open_changer: Callable[[], AbstractAsyncContextManager[ModelConnectionGrantChanger]],
    open_reader: Callable[[], AbstractAsyncContextManager[ModelConnectionGrantsReader]],
) -> APIRouter:
    router = APIRouter(route_class=ActionGrantRoute)
    errors = (
        human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(CONFLICT_PROBLEM)
        | problem_responses(STALE_REVISION_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM)
    )
    key_dependency = IdempotencyKeyDependency()

    @router.get(
        _GRANTS, tags=["access"], operation_id="listModelConnectionActionGrants", responses=errors
    )
    async def grants(
        model_connection_id: UUID,
        action_id: Annotated[ModelConnectionAction, Query(alias="actionId")],
        pagination: Annotated[PaginationQuery, Depends()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> PageResponse[ModelConnectionActionGrantItemResponse]:
        async with open_reader() as reader:
            page = await reader.list_grants(
                access,
                ModelConnectionId(model_connection_id),
                action_id,
                pagination.limit,
                pagination.cursor,
            )
        return PageResponse[ModelConnectionActionGrantItemResponse](
            items=[
                ModelConnectionActionGrantItemResponse(
                    model_connection_id=model_connection_id,
                    recipient_principal_id=item.recipient_id.value,
                    action_id=action_id,
                    can_grant=item.can_grant,
                )
                for item in page.items
            ],
            next_cursor=page.next_cursor,
        )

    async def change(
        model_connection_id: UUID,
        recipient_principal_id: UUID,
        action: ModelConnectionAction,
        revision: int,
        can_grant: bool | None,
        access: AccessContextDTO,
        key: IdempotencyKey,
    ) -> ModelConnectionGrantResultDTO:
        method = HttpMethod.DELETE if can_grant is None else HttpMethod.PUT
        route = _ASSIGNMENT.format(
            model_connection_id=model_connection_id,
            recipient_principal_id=recipient_principal_id,
            action_id=action.value,
        )
        async with open_changer() as changer:
            return await changer.change(
                access,
                ChangeModelConnectionGrantCommand(
                    ModelConnectionId(model_connection_id),
                    PrincipalId(recipient_principal_id),
                    action,
                    revision,
                    can_grant,
                ),
                IdempotencyContextDTO(method, route, key),
            )

    @router.put(
        _ASSIGNMENT,
        tags=["access"],
        operation_id="setModelConnectionActionGrant",
        status_code=201,
        responses={
            200: {
                "model": ModelConnectionActionGrantResponse,
                "description": "Changed or unchanged assignment.",
            }
        }
        | errors
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def put(
        model_connection_id: UUID,
        recipient_principal_id: UUID,
        action_id: ModelConnectionAction,
        body: ModelConnectionActionGrantRequest,
        response: Response,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> ModelConnectionActionGrantResponse:
        result = await change(
            model_connection_id,
            recipient_principal_id,
            action_id,
            body.expected_access_revision,
            body.can_grant,
            access,
            key,
        )
        if result.can_grant is None:
            raise RuntimeError("Assignment changed into removal.")
        response.status_code = result.status_code
        return ModelConnectionActionGrantResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            model_connection_id=result.target.model_connection_id.value,
            recipient_principal_id=result.recipient_id.value,
            action_id=result.action,
            can_grant=result.can_grant,
            access_revision=result.access_revision,
            changed=result.changed,
        )

    @router.delete(
        _ASSIGNMENT,
        tags=["access"],
        operation_id="removeModelConnectionActionGrant",
        responses=errors,
    )
    async def remove(
        model_connection_id: UUID,
        recipient_principal_id: UUID,
        action_id: ModelConnectionAction,
        expected_access_revision: Annotated[
            int,
            Query(
                alias="expectedAccessRevision",
                ge=0,
                le=RevisionValidation.MAX_VALUE,
                json_schema_extra={"format": "int64"},
            ),
        ],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> ModelConnectionActionGrantRemovalResponse:
        result = await change(
            model_connection_id,
            recipient_principal_id,
            action_id,
            expected_access_revision,
            None,
            access,
            key,
        )
        if result.can_grant is not None:
            raise RuntimeError("Removal changed into assignment.")
        return ModelConnectionActionGrantRemovalResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            model_connection_id=result.target.model_connection_id.value,
            recipient_principal_id=result.recipient_id.value,
            action_id=result.action,
            removed=True,
            access_revision=result.access_revision,
            changed=result.changed,
        )

    return router
