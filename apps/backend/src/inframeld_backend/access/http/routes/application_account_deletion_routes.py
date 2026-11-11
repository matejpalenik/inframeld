from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.application_account_deleter import (
    ApplicationAccountDeleter,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.mappers.application_account_deletion_mapper import (
    ApplicationAccountDeletionMapper,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.responses.application_account_deletion_response import (
    ApplicationAccountDeletionResponse,
)
from inframeld_backend.access.http.routes.application_account_route import ApplicationAccountRoute
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
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses


def create_application_account_deletion_router(
    authenticate: ProductAccessDependency,
    open_deleter: Callable[[], AbstractAsyncContextManager[ApplicationAccountDeleter]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=ApplicationAccountRoute)
    key_dependency = IdempotencyKeyDependency()
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

    @router.delete(
        "/projects/{project_id}/application-accounts/{application_principal_id}",
        operation_id="deleteApplicationAccount",
        tags=["access"],
        status_code=200,
        responses=errors,
    )
    async def delete(
        project_id: UUID,
        application_principal_id: UUID,
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
    ) -> ApplicationAccountDeletionResponse:
        project, application = ProjectId(project_id), PrincipalId(application_principal_id)
        async with open_deleter() as deleter:
            result = await deleter.delete(
                access=access,
                command=ApplicationAccountDeletionMapper.command(
                    project, application, expected_access_revision
                ),
                context=ApplicationAccountDeletionMapper.context(project, application, key),
            )
        return ApplicationAccountDeletionMapper.response(result)

    return router
