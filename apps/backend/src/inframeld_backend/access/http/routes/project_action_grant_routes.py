from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.project_action_grants_reader import (
    ProjectActionGrantsReader,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.mappers.project_action_grant_mapper import (
    ProjectActionGrantMapper,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.responses.project_action_grant_item_response import (
    ProjectActionGrantItemResponse,
)
from inframeld_backend.access.http.routes.action_grant_route import ActionGrantRoute
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INVALID_INPUT_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery
from inframeld_backend.shared.http.responses.page_response import PageResponse


def create_project_action_grant_router(
    authenticate: ProductAccessDependency,
    open_reader: Callable[[], AbstractAsyncContextManager[ProjectActionGrantsReader]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=ActionGrantRoute)

    @router.get(
        "/projects/{project_id}/grants",
        tags=["access"],
        operation_id="listProjectActionGrants",
        responses=human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM),
    )
    async def grants(
        project_id: UUID,
        action_id: Annotated[str, Query(alias="actionId", min_length=1, max_length=100)],
        pagination: Annotated[PaginationQuery, Depends()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> PageResponse[ProjectActionGrantItemResponse]:
        query = ProjectActionGrantMapper.query(
            project_id=project_id, action_id=action_id, pagination=pagination
        )
        async with open_reader() as reader:
            result = await reader.list_grants(access=access, query=query)
        return ProjectActionGrantMapper.response(result)

    return router
