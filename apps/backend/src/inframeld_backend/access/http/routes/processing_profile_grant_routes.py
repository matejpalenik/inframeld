from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from inframeld_backend.access.application.commands.change_processing_profile_grant_command import (
    ChangeProcessingProfileGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.processing_profile_grant_result_dto import (
    ProcessingProfileGrantResultDTO,
)
from inframeld_backend.access.application.protocols.processing_profile_grant_changer import (
    ProcessingProfileGrantChanger,
)
from inframeld_backend.access.application.protocols.processing_profile_grants_reader import (
    ProcessingProfileGrantsReader,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.processing_profile_action_grant_request import (
    ProcessingProfileActionGrantRequest,
)
from inframeld_backend.access.http.responses.processing_profile_action_grant_item_response import (
    ProcessingProfileActionGrantItemResponse,
)
from inframeld_backend.access.http.responses.processing_profile_action_grant_removal_response import (
    ProcessingProfileActionGrantRemovalResponse,
)
from inframeld_backend.access.http.responses.processing_profile_action_grant_response import (
    ProcessingProfileActionGrantResponse,
)
from inframeld_backend.access.http.routes.action_grant_route import ActionGrantRoute
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
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

_GRANTS = "/v1/processing-profiles/{processing_profile_id}/grants"
_ASSIGNMENT = _GRANTS + "/{recipient_principal_id}/{action_id}"


def create_processing_profile_grant_router(
    authenticate: ProductAccessDependency,
    open_changer: Callable[[], AbstractAsyncContextManager[ProcessingProfileGrantChanger]],
    open_reader: Callable[[], AbstractAsyncContextManager[ProcessingProfileGrantsReader]],
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
        _GRANTS, tags=["access"], operation_id="listProcessingProfileActionGrants", responses=errors
    )
    async def grants(
        processing_profile_id: UUID,
        action_id: Annotated[ProcessingProfileAction, Query(alias="actionId")],
        pagination: Annotated[PaginationQuery, Depends()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> PageResponse[ProcessingProfileActionGrantItemResponse]:
        async with open_reader() as reader:
            page = await reader.list_grants(
                access,
                ProcessingProfileId(processing_profile_id),
                action_id,
                pagination.limit,
                pagination.cursor,
            )
        return PageResponse[ProcessingProfileActionGrantItemResponse](
            items=[
                ProcessingProfileActionGrantItemResponse(
                    processing_profile_id=processing_profile_id,
                    recipient_principal_id=item.recipient_id.value,
                    action_id=action_id,
                    can_grant=item.can_grant,
                )
                for item in page.items
            ],
            next_cursor=page.next_cursor,
        )

    async def change(
        processing_profile_id: UUID,
        recipient_principal_id: UUID,
        action: ProcessingProfileAction,
        revision: int,
        can_grant: bool | None,
        access: AccessContextDTO,
        key: IdempotencyKey,
    ) -> ProcessingProfileGrantResultDTO:
        method = HttpMethod.DELETE if can_grant is None else HttpMethod.PUT
        route = _ASSIGNMENT.format(
            processing_profile_id=processing_profile_id,
            recipient_principal_id=recipient_principal_id,
            action_id=action.value,
        )
        async with open_changer() as changer:
            return await changer.change(
                access,
                ChangeProcessingProfileGrantCommand(
                    ProcessingProfileId(processing_profile_id),
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
        operation_id="setProcessingProfileActionGrant",
        status_code=201,
        responses={
            200: {
                "model": ProcessingProfileActionGrantResponse,
                "description": "Changed or unchanged assignment.",
            }
        }
        | errors
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def put(
        processing_profile_id: UUID,
        recipient_principal_id: UUID,
        action_id: ProcessingProfileAction,
        body: ProcessingProfileActionGrantRequest,
        response: Response,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> ProcessingProfileActionGrantResponse:
        result = await change(
            processing_profile_id,
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
        return ProcessingProfileActionGrantResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            processing_profile_id=result.target.processing_profile_id.value,
            recipient_principal_id=result.recipient_id.value,
            action_id=result.action,
            can_grant=result.can_grant,
            access_revision=result.access_revision,
            changed=result.changed,
        )

    @router.delete(
        _ASSIGNMENT,
        tags=["access"],
        operation_id="removeProcessingProfileActionGrant",
        responses=errors,
    )
    async def remove(
        processing_profile_id: UUID,
        recipient_principal_id: UUID,
        action_id: ProcessingProfileAction,
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
    ) -> ProcessingProfileActionGrantRemovalResponse:
        result = await change(
            processing_profile_id,
            recipient_principal_id,
            action_id,
            expected_access_revision,
            None,
            access,
            key,
        )
        if result.can_grant is not None:
            raise RuntimeError("Removal changed into assignment.")
        return ProcessingProfileActionGrantRemovalResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            processing_profile_id=result.target.processing_profile_id.value,
            recipient_principal_id=result.recipient_id.value,
            action_id=result.action,
            removed=True,
            access_revision=result.access_revision,
            changed=result.changed,
        )

    return router
