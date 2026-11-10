from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.project_upload_default_changer import (
    ProjectUploadDefaultChanger,
)
from inframeld_backend.access.application.protocols.project_upload_default_reader import (
    ProjectUploadDefaultReader,
)
from inframeld_backend.access.application.queries.get_project_upload_default_query import (
    GetProjectUploadDefaultQuery,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.mappers.project_upload_default_mapper import (
    ProjectUploadDefaultMapper,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.project_upload_default_request import (
    ProjectUploadDefaultRequest,
)
from inframeld_backend.access.http.responses.project_upload_default_change_response import (
    ProjectUploadDefaultChangeResponse,
)
from inframeld_backend.access.http.responses.project_upload_default_response import (
    ProjectUploadDefaultResponse,
)
from inframeld_backend.access.http.routes.project_upload_default_route import (
    ProjectUploadDefaultRoute,
)
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


def create_project_upload_default_router(
    authenticate: ProductAccessDependency,
    open_reader: Callable[[], AbstractAsyncContextManager[ProjectUploadDefaultReader]],
    open_changer: Callable[[], AbstractAsyncContextManager[ProjectUploadDefaultChanger]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=ProjectUploadDefaultRoute)
    errors = human_authentication_responses()
    for problem in (
        ACCESS_DENIED_PROBLEM,
        CONFLICT_PROBLEM,
        DEPENDENCY_UNAVAILABLE_PROBLEM,
        INVALID_INPUT_PROBLEM,
        RESOURCE_NOT_FOUND_PROBLEM,
        VALIDATION_ERROR_PROBLEM,
    ):
        errors |= problem_responses(problem)
    key_dependency = IdempotencyKeyDependency()

    @router.get(
        "/projects/{project_id}/upload-defaults",
        tags=["access"],
        operation_id="getProjectUploadDefaults",
        responses=errors,
    )
    async def get(
        project_id: UUID, access: Annotated[AccessContextDTO, Depends(authenticate)]
    ) -> ProjectUploadDefaultResponse:
        async with open_reader() as reader:
            result = await reader.get(
                access=access, query=GetProjectUploadDefaultQuery(ProjectId(project_id))
            )
        return ProjectUploadDefaultMapper.current(result)

    @router.put(
        "/projects/{project_id}/upload-defaults",
        tags=["access"],
        operation_id="setProjectUploadDefaults",
        responses=errors
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def set_default(
        project_id: UUID,
        body: ProjectUploadDefaultRequest,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> ProjectUploadDefaultChangeResponse:
        command = ProjectUploadDefaultMapper.command(project_id, body)
        async with open_changer() as changer:
            result = await changer.set(
                access=access,
                command=command,
                context=ProjectUploadDefaultMapper.context(project_id, key),
            )
        return ProjectUploadDefaultMapper.changed(result)

    return router
