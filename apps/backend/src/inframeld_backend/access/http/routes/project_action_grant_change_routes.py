from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.project_grant_changer import ProjectGrantChanger
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.mappers.project_action_grant_change_mapper import (
    ProjectActionGrantChangeMapper,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.project_action_grant_request import (
    ProjectActionGrantRequest,
)
from inframeld_backend.access.http.responses.project_action_grant_removal_response import (
    ProjectActionGrantRemovalResponse,
)
from inframeld_backend.access.http.responses.project_action_grant_response import (
    ProjectActionGrantResponse,
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


def create_project_action_grant_change_router(
    authenticate: ProductAccessDependency,
    open_changer: Callable[[], AbstractAsyncContextManager[ProjectGrantChanger]],
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

    @router.put(
        "/projects/{project_id}/grants/{recipient_principal_id}/{action_id}",
        tags=["access"],
        operation_id="setProjectActionGrant",
        status_code=201,
        responses={
            200: {
                "model": ProjectActionGrantResponse,
                "description": "Changed or unchanged existing assignment.",
            }
        }
        | errors
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def assign(
        project_id: UUID,
        recipient_principal_id: UUID,
        action_id: str,
        body: ProjectActionGrantRequest,
        response: Response,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> ProjectActionGrantResponse:
        command = ProjectActionGrantChangeMapper.set_command(
            project_id, recipient_principal_id, action_id, body
        )
        context = ProjectActionGrantChangeMapper.context(command, HttpMethod.PUT, key)
        async with open_changer() as service:
            result = await service.set_action_grant(access=access, command=command, context=context)
        response.status_code = result.status_code
        return ProjectActionGrantChangeMapper.set_response(result)

    @router.delete(
        "/projects/{project_id}/grants/{recipient_principal_id}/{action_id}",
        tags=["access"],
        operation_id="removeProjectActionGrant",
        responses=errors,
    )
    async def remove(
        project_id: UUID,
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
    ) -> ProjectActionGrantRemovalResponse:
        command = ProjectActionGrantChangeMapper.remove_command(
            project_id, recipient_principal_id, action_id, expected_access_revision
        )
        context = ProjectActionGrantChangeMapper.context(command, HttpMethod.DELETE, key)
        async with open_changer() as service:
            result = await service.remove_action_grant(
                access=access, command=command, context=context
            )
        return ProjectActionGrantChangeMapper.remove_response(result)

    return router
