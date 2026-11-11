from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.project_deleter import ProjectDeleter
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.mappers.project_deletion_mapper import ProjectDeletionMapper
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.responses.project_deletion_admission_response import (
    ProjectDeletionAdmissionResponse,
)
from inframeld_backend.access.http.routes.project_deletion_route import ProjectDeletionRoute
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_id import RequestId
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
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses


def create_project_deletion_router(
    authenticate: ProductAccessDependency,
    open_deleter: Callable[[], AbstractAsyncContextManager[ProjectDeleter]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=ProjectDeletionRoute)
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

    @router.delete(
        "/projects/{project_id}",
        tags=["access"],
        operation_id="deleteProject",
        status_code=202,
        responses=errors,
    )
    async def delete(
        project_id: UUID,
        expected_access_revision: Annotated[
            int,
            Query(
                alias="expectedAccessRevision",
                ge=0,
                le=RevisionValidation.MAX_VALUE,
                json_schema_extra={"format": "int64"},
            ),
        ],
        request: Request,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> ProjectDeletionAdmissionResponse:
        request_id: object = getattr(request.state, "request_id", None)
        if not isinstance(request_id, RequestId):
            raise RuntimeError("Project deletion requires trusted request correlation.")
        async with open_deleter() as deleter:
            result = await deleter.delete(
                access=access,
                command=DeleteProjectCommand(ProjectId(project_id), expected_access_revision),
                context=IdempotencyContextDTO(HttpMethod.DELETE, f"/v1/projects/{project_id}", key),
                request_id=request_id,
            )
        return ProjectDeletionMapper.admission(result)

    return router
