from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated, override
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.project_grant_recipients_reader import (
    ProjectGrantRecipientsReader,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.enums.grant_target_kind import GrantTargetKind
from inframeld_backend.access.http.mappers.project_grant_recipients_mapper import (
    ProjectGrantRecipientsMapper,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.responses.grant_recipient_response import GrantRecipientResponse
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
from inframeld_backend.shared.http.responses.page_response import PageResponse


class _GrantRecipientsRoute(APIRoute):
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

        if self.methods is not None and scope["method"] not in self.methods:
            await super().handle(scope, receive, private_response)
            return
        request = Request(scope, receive)
        invalid = any(
            key not in {"targetKind", "targetId", "actionId", "limit", "cursor"}
            or len(request.query_params.getlist(key)) != 1
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


def create_project_grant_recipients_router(
    authenticate: HumanSessionDependency,
    open_reader: Callable[[], AbstractAsyncContextManager[ProjectGrantRecipientsReader]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=_GrantRecipientsRoute)

    @router.get(
        "/projects/{project_id}/grant-recipients",
        tags=["access"],
        operation_id="listProjectGrantRecipients",
        responses=human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM),
    )
    async def recipients(
        project_id: UUID,
        target_kind: Annotated[GrantTargetKind, Query(alias="targetKind")],
        target_id: Annotated[UUID, Query(alias="targetId")],
        action_id: Annotated[str, Query(alias="actionId", min_length=1, max_length=100)],
        pagination: Annotated[PaginationQuery, Depends()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> PageResponse[GrantRecipientResponse]:
        query = ProjectGrantRecipientsMapper.query(
            project_id=project_id,
            target_kind=target_kind,
            target_id=target_id,
            action_id=action_id,
            pagination=pagination,
        )
        async with open_reader() as reader:
            page = await reader.list_recipients(access=access, query=query)
        return ProjectGrantRecipientsMapper.response(page)

    return router
