from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.application_key_revoker import (
    ApplicationKeyRevoker,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.mappers.application_key_revocation_mapper import (
    ApplicationKeyRevocationMapper,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.application_key_revocation_request import (
    ApplicationKeyRevocationRequest,
)
from inframeld_backend.access.http.responses.application_key_revocation_response import (
    ApplicationKeyRevocationResponse,
)
from inframeld_backend.access.http.routes.application_account_route import ApplicationAccountRoute
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


def create_application_key_revocation_router(
    authenticate: ProductAccessDependency,
    open_revoker: Callable[[], AbstractAsyncContextManager[ApplicationKeyRevoker]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=ApplicationAccountRoute)
    errors = human_authentication_responses()
    for problem in (
        ACCESS_DENIED_PROBLEM,
        CONFLICT_PROBLEM,
        DEPENDENCY_UNAVAILABLE_PROBLEM,
        INVALID_INPUT_PROBLEM,
        RESOURCE_NOT_FOUND_PROBLEM,
        VALIDATION_ERROR_PROBLEM,
        for_http_status(413),
        for_http_status(415),
    ):
        errors |= problem_responses(problem)
    key_dependency = IdempotencyKeyDependency()

    @router.post(
        "/projects/{project_id}/application-accounts/{application_principal_id}/keys/{key_id}/revoke",
        tags=["access"],
        operation_id="revokeApplicationKey",
        responses=errors,
    )
    async def revoke(
        project_id: UUID,
        application_principal_id: UUID,
        key_id: UUID,
        body: ApplicationKeyRevocationRequest,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        original: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> ApplicationKeyRevocationResponse:
        project, application, key = (
            ProjectId(project_id),
            PrincipalId(application_principal_id),
            ApplicationKeyId(key_id),
        )
        async with open_revoker() as revoker:
            result = await revoker.revoke(
                access=access,
                command=ApplicationKeyRevocationMapper.command(project, application, key, body),
                context=ApplicationKeyRevocationMapper.context(project, application, key, original),
            )
        return ApplicationKeyRevocationMapper.response(result)

    return router
