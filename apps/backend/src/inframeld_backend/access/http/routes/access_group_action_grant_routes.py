from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.access_group_action_grant_changer import (
    AccessGroupActionGrantChanger,
)
from inframeld_backend.access.application.protocols.access_group_action_grants_reader import (
    AccessGroupActionGrantsReader,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.mappers.access_group_action_grant_mapper import (
    AccessGroupActionGrantMapper,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
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
from inframeld_backend.access.http.routes.action_grant_route import ActionGrantRoute
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    CONFLICT_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INVALID_INPUT_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.dependencies.idempotency_key_dependency import (
    IdempotencyKeyDependency,
)
from inframeld_backend.shared.http.mappers.problem_mapper import for_http_status
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery
from inframeld_backend.shared.http.responses.page_response import PageResponse


def create_access_group_action_grant_router(
    authenticate: HumanSessionDependency,
    open_changer: Callable[[], AbstractAsyncContextManager[AccessGroupActionGrantChanger]],
    open_reader: Callable[[], AbstractAsyncContextManager[AccessGroupActionGrantsReader]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=ActionGrantRoute)
    key_dependency = IdempotencyKeyDependency()
    errors = (
        human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(CONFLICT_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM)
    )

    @router.get(
        "/projects/{project_id}/access-groups/{access_group_id}/grants",
        tags=["access"],
        operation_id="listAccessGroupActionGrants",
        responses=errors,
    )
    async def grants(
        project_id: UUID,
        access_group_id: UUID,
        action_id: Annotated[str, Query(alias="actionId", min_length=1, max_length=100)],
        pagination: Annotated[PaginationQuery, Depends()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> PageResponse[AccessGroupActionGrantItemResponse]:
        query = AccessGroupActionGrantMapper.query(
            project_id=project_id,
            access_group_id=access_group_id,
            action_id=action_id,
            pagination=pagination,
        )
        async with open_reader() as reader:
            result = await reader.list_grants(access=access, query=query)
        return AccessGroupActionGrantMapper.page_response(result)

    @router.put(
        "/projects/{project_id}/access-groups/{access_group_id}/grants/{recipient_principal_id}/{action_id}",
        tags=["access"],
        operation_id="setAccessGroupActionGrant",
        status_code=201,
        responses={
            200: {
                "model": AccessGroupActionGrantResponse,
                "description": "Changed or unchanged existing assignment.",
            }
        }
        | errors
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def assign(
        project_id: UUID,
        access_group_id: UUID,
        recipient_principal_id: UUID,
        action_id: str,
        body: AccessGroupActionGrantRequest,
        response: Response,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> AccessGroupActionGrantResponse:
        command = AccessGroupActionGrantMapper.set_command(
            project_id=project_id,
            access_group_id=access_group_id,
            recipient_principal_id=recipient_principal_id,
            action_id=action_id,
            body=body,
        )
        context = AccessGroupActionGrantMapper.context(
            command=command, method=HttpMethod.PUT, key=key
        )
        async with open_changer() as changer:
            result = await changer.set_grant(access=access, command=command, context=context)
        response.status_code = result.status_code
        return AccessGroupActionGrantMapper.set_response(result)

    @router.delete(
        "/projects/{project_id}/access-groups/{access_group_id}/grants/{recipient_principal_id}/{action_id}",
        tags=["access"],
        operation_id="removeAccessGroupActionGrant",
        responses=errors,
    )
    async def remove(
        project_id: UUID,
        access_group_id: UUID,
        recipient_principal_id: UUID,
        action_id: str,
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
    ) -> AccessGroupActionGrantRemovalResponse:
        command = AccessGroupActionGrantMapper.remove_command(
            project_id=project_id,
            access_group_id=access_group_id,
            recipient_principal_id=recipient_principal_id,
            action_id=action_id,
            expected_access_revision=expected_access_revision,
        )
        context = AccessGroupActionGrantMapper.context(
            command=command, method=HttpMethod.DELETE, key=key
        )
        async with open_changer() as changer:
            result = await changer.remove_grant(access=access, command=command, context=context)
        return AccessGroupActionGrantMapper.remove_response(result)

    return router
