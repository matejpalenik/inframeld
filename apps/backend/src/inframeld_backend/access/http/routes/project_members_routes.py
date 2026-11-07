from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated, override
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.project_members_reader import (
    ProjectMembersReader,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.mappers.project_members_mapper import ProjectMembersMapper
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.responses.project_members_page_response import (
    ProjectMembersPageResponse,
)
from inframeld_backend.shared.http.builders.problem_response import build_problem_response
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INVALID_INPUT_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery


class _ProjectMembersRoute(APIRoute):
    """Protect this read's query/body boundary and private responses."""

    @override
    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def private_response(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"cache-control"
                ]
                message = {**message, "headers": headers + [(b"cache-control", b"no-store")]}
            await send(message)

        request = Request(scope, receive)
        keys = list(request.query_params)
        invalid = any(
            key not in {"limit", "cursor"} or len(request.query_params.getlist(key)) != 1
            for key in keys
        )
        if not invalid:
            async for chunk in request.stream():
                if chunk:
                    invalid = True
                    break
        if invalid:
            await build_problem_response(request, INVALID_INPUT_PROBLEM)(
                scope, receive, private_response
            )
            return
        await super().handle(scope, receive, private_response)


def create_project_members_router(
    authenticate: ProductAccessDependency,
    open_reader: Callable[[], AbstractAsyncContextManager[ProjectMembersReader]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=_ProjectMembersRoute)

    @router.get(
        "/projects/{project_id}/members",
        tags=["access"],
        operation_id="listProjectMembers",
        responses=human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM),
    )
    async def members(
        project_id: UUID,
        pagination: Annotated[PaginationQuery, Query()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> ProjectMembersPageResponse:
        async with open_reader() as reader:
            result = await reader.list_members(
                access=access,
                query=ProjectMembersMapper.query(project_id=project_id, pagination=pagination),
            )
        return ProjectMembersMapper.response(result)

    return router
