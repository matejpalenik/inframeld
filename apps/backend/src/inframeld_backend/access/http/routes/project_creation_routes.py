from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated

from fastapi import APIRouter, Depends

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.project_creator import ProjectCreator
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.mappers.project_creation_mapper import ProjectCreationMapper
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.project_creation_request import ProjectCreationRequest
from inframeld_backend.access.http.responses.project_creation_response import (
    ProjectCreationResponse,
)
from inframeld_backend.access.http.routes.project_creation_route import ProjectCreationRoute
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
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


def create_project_creation_router(
    authenticate: HumanSessionDependency,
    open_creator: Callable[[], AbstractAsyncContextManager[ProjectCreator]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=ProjectCreationRoute)
    key_dependency = IdempotencyKeyDependency()

    @router.post(
        "/projects",
        tags=["access"],
        operation_id="createProject",
        status_code=201,
        responses=human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(CONFLICT_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM)
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def create(
        body: ProjectCreationRequest,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> ProjectCreationResponse:
        async with open_creator() as service:
            result = await service.create(
                access=access,
                command=ProjectCreationMapper.command(body),
                context=ProjectCreationMapper.context(key),
            )
        return ProjectCreationMapper.response(result)

    return router
