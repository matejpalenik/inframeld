from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated, override
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.my_project_access_reader import (
    MyProjectAccessReader,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.mappers.my_project_access_mapper import MyProjectAccessMapper
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.responses.my_project_access_response import (
    MyProjectAccessResponse,
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


class _MyProjectAccessRoute(APIRoute):
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
        invalid = any(
            key not in {"limit", "cursor"} or len(request.query_params.getlist(key)) != 1
            for key in request.query_params
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


def create_my_project_access_router(
    authenticate: HumanSessionDependency,
    open_reader: Callable[[], AbstractAsyncContextManager[MyProjectAccessReader]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=_MyProjectAccessRoute)

    @router.get(
        "/projects/{project_id}/my-access",
        tags=["access"],
        operation_id="getMyProjectAccess",
        responses=human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM),
    )
    async def own_access(
        project_id: UUID,
        pagination: Annotated[PaginationQuery, Depends()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> MyProjectAccessResponse:
        query = MyProjectAccessMapper.query(project_id=project_id, pagination=pagination)
        async with open_reader() as reader:
            page = await reader.get_access(access=access, query=query)
        return MyProjectAccessMapper.response(page)

    return router
