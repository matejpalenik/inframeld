"""Expose the supported project grant command over authenticated HTTP."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.project_grant_changer import ProjectGrantChanger
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.mappers.project_use_only_grant_mapper import (
    ProjectUseOnlyGrantMapper,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.project_use_only_grant_request import (
    ProjectUseOnlyGrantRequest,
)
from inframeld_backend.access.http.responses.project_use_only_grant_response import (
    ProjectUseOnlyGrantResponse,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    CONFLICT_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.dependencies.idempotency_key_dependency import (
    IdempotencyKeyDependency,
)
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses

_GRANT_PROBLEM_RESPONSES = (
    human_authentication_responses()
    | problem_responses(ACCESS_DENIED_PROBLEM)
    | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
    | problem_responses(CONFLICT_PROBLEM)
    | problem_responses(VALIDATION_ERROR_PROBLEM)
    | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
)
_GRANT_PROBLEM_RESPONSES[409]["description"] = (
    "Conflict: stale_revision, idempotency_key_reused, idempotency_in_progress, or conflict."
)


def create_project_grant_router(
    authenticate: HumanSessionDependency,
    open_grant_change: Callable[[], AbstractAsyncContextManager[ProjectGrantChanger]],
) -> APIRouter:
    """Register a use-only grant command with its trusted request dependencies."""
    router = APIRouter(prefix="/v1")
    key_dependency = IdempotencyKeyDependency()

    @router.post(
        "/projects/{project_id}/grants",
        tags=["access"],
        operation_id="assignProjectUseOnlyGrant",
        status_code=HTTPStatus.CREATED,
        responses=_GRANT_PROBLEM_RESPONSES,
    )
    async def assign_use_only(
        project_id: UUID,
        body: ProjectUseOnlyGrantRequest,
        idempotency_key: Annotated[IdempotencyKey, Depends(key_dependency)],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> ProjectUseOnlyGrantResponse:
        command = ProjectUseOnlyGrantMapper.to_command(project_id=project_id, request=body)
        context = ProjectUseOnlyGrantMapper.to_operation_context(idempotency_key)
        # Provider verification and CSRF finish before opening the operation's session.
        async with open_grant_change() as service:
            result = await service.assign_use_only(access=access, command=command, context=context)
        response = ProjectUseOnlyGrantMapper.to_response(command=command, result=result)
        return response

    return router
