from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from starlette.requests import Request
from starlette.responses import Response

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.errors.retired_project_name_error import (
    RetiredProjectNameError,
)
from inframeld_backend.access.application.protocols.project_metadata_changer import (
    ProjectMetadataChanger,
)
from inframeld_backend.access.application.protocols.project_metadata_reader import (
    ProjectMetadataReader,
)
from inframeld_backend.access.application.protocols.project_name_resolver import ProjectNameResolver
from inframeld_backend.access.application.queries.get_project_metadata_query import (
    GetProjectMetadataQuery,
)
from inframeld_backend.access.application.queries.resolve_project_name_query import (
    ResolveProjectNameQuery,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.mappers.project_metadata_mapper import ProjectMetadataMapper
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.project_metadata_update_request import (
    ProjectMetadataUpdateRequest,
)
from inframeld_backend.access.http.responses.project_metadata_change_response import (
    ProjectMetadataChangeResponse,
)
from inframeld_backend.access.http.responses.project_metadata_response import (
    ProjectMetadataResponse,
)
from inframeld_backend.access.http.responses.project_name_resolution_response import (
    ProjectNameResolutionResponse,
)
from inframeld_backend.access.http.routes.project_metadata_route import ProjectMetadataRoute
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.http.builders.problem_response import build_problem_response
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

_PROBLEMS = (
    human_authentication_responses()
    | problem_responses(ACCESS_DENIED_PROBLEM)
    | problem_responses(CONFLICT_PROBLEM)
    | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
    | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
    | problem_responses(VALIDATION_ERROR_PROBLEM)
    | problem_responses(INVALID_INPUT_PROBLEM)
)


def create_project_metadata_router(
    authenticate: HumanSessionDependency,
    open_reader: Callable[[], AbstractAsyncContextManager[ProjectMetadataReader]],
    open_changer: Callable[[], AbstractAsyncContextManager[ProjectMetadataChanger]],
    open_resolver: Callable[[], AbstractAsyncContextManager[ProjectNameResolver]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=ProjectMetadataRoute)
    key_dependency = IdempotencyKeyDependency()

    @router.get(
        "/projects/by-name/{name}",
        tags=["access"],
        operation_id="resolveProjectName",
        responses=_PROBLEMS,
        response_model=ProjectNameResolutionResponse,
    )
    async def resolve(
        request: Request,
        name: Annotated[
            str,
            Path(
                min_length=1,
                max_length=63,
                pattern="^[a-z](?:[a-z0-9-]*[a-z0-9])?$",
                description="Exact Project selector in the current installation and Organization.",
            ),
        ],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> ProjectNameResolutionResponse | Response:
        try:
            async with open_resolver() as service:
                result = await service.resolve(
                    access=access, query=ResolveProjectNameQuery(ResourceName(name))
                )
        except RetiredProjectNameError as error:
            return build_problem_response(request, ProjectMetadataMapper.retired(error))
        return ProjectMetadataMapper.resolved(result)

    @router.get(
        "/projects/{project_id}/metadata",
        tags=["access"],
        operation_id="getProjectMetadata",
        responses=_PROBLEMS,
    )
    async def get(
        project_id: UUID, access: Annotated[AccessContextDTO, Depends(authenticate)]
    ) -> ProjectMetadataResponse:
        async with open_reader() as service:
            result = await service.get(
                access=access, query=GetProjectMetadataQuery(ProjectId(project_id))
            )
        return ProjectMetadataMapper.metadata(result)

    @router.patch(
        "/projects/{project_id}/metadata",
        tags=["access"],
        operation_id="updateProjectMetadata",
        responses=_PROBLEMS
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def update(
        project_id: UUID,
        body: ProjectMetadataUpdateRequest,
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> ProjectMetadataChangeResponse:
        command = ProjectMetadataMapper.to_command(project_id, body)
        async with open_changer() as service:
            result = await service.update(
                access=access, command=command, context=ProjectMetadataMapper.context(key)
            )
        return ProjectMetadataMapper.changed(result)

    return router
