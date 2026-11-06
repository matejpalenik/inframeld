from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.application_account_creator import (
    ApplicationAccountCreator,
)
from inframeld_backend.access.application.protocols.application_account_reader import (
    ApplicationAccountReader,
)
from inframeld_backend.access.application.queries.list_application_keys_query import (
    ListApplicationKeysQuery,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.mappers.application_account_mapper import (
    ApplicationAccountMapper,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.application_account_creation_request import (
    ApplicationAccountCreationRequest,
)
from inframeld_backend.access.http.responses.application_account_creation_response import (
    ApplicationAccountCreationResponse,
)
from inframeld_backend.access.http.responses.application_account_metadata_response import (
    ApplicationAccountMetadataResponse,
)
from inframeld_backend.access.http.responses.application_key_metadata_response import (
    ApplicationKeyMetadataResponse,
)
from inframeld_backend.access.http.routes.application_account_route import ApplicationAccountRoute
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
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
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery
from inframeld_backend.shared.http.responses.page_response import PageResponse


def create_application_account_router(
    authenticate: HumanSessionDependency,
    open_creator: Callable[[], AbstractAsyncContextManager[ApplicationAccountCreator]],
    open_reader: Callable[[], AbstractAsyncContextManager[ApplicationAccountReader]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=ApplicationAccountRoute)
    errors = (
        human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(CONFLICT_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM)
    )
    key_dependency = IdempotencyKeyDependency()

    @router.post(
        "/projects/{project_id}/application-accounts",
        tags=["access"],
        operation_id="createApplicationAccount",
        status_code=201,
        responses=errors
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def create(
        project_id: UUID,
        body: ApplicationAccountCreationRequest,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> ApplicationAccountCreationResponse:
        project = ProjectId(project_id)
        async with open_creator() as creator:
            result = await creator.create(
                access=access,
                command=ApplicationAccountMapper.command(project, body),
                context=ApplicationAccountMapper.context(project, key),
            )
        return ApplicationAccountMapper.creation(result)

    @router.get(
        "/projects/{project_id}/application-accounts/resolve",
        tags=["access"],
        operation_id="resolveApplicationAccount",
        responses=errors,
    )
    async def resolve(
        project_id: UUID,
        name: Annotated[
            str, Query(min_length=1, max_length=63, pattern="^[a-z](?:[a-z0-9-]*[a-z0-9])?$")
        ],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> ApplicationAccountMetadataResponse:
        async with open_reader() as reader:
            account = await reader.resolve_account(
                access=access, project_id=ProjectId(project_id), name=ResourceName(name)
            )
        return ApplicationAccountMapper.metadata(account)

    @router.get(
        "/projects/{project_id}/application-accounts/{application_principal_id}",
        tags=["access"],
        operation_id="getApplicationAccount",
        responses=errors,
    )
    async def get(
        project_id: UUID,
        application_principal_id: UUID,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> ApplicationAccountMetadataResponse:
        async with open_reader() as reader:
            account = await reader.get_account(
                access=access,
                project_id=ProjectId(project_id),
                principal_id=PrincipalId(application_principal_id),
            )
        return ApplicationAccountMapper.metadata(account)

    @router.get(
        "/projects/{project_id}/application-accounts/{application_principal_id}/keys",
        tags=["access"],
        operation_id="listApplicationKeys",
        responses=errors,
    )
    async def keys(
        project_id: UUID,
        application_principal_id: UUID,
        pagination: Annotated[PaginationQuery, Query()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> PageResponse[ApplicationKeyMetadataResponse]:
        async with open_reader() as reader:
            page = await reader.list_keys(
                access=access,
                query=ListApplicationKeysQuery(
                    ProjectId(project_id),
                    PrincipalId(application_principal_id),
                    pagination.limit,
                    pagination.cursor,
                ),
            )
        return ApplicationAccountMapper.page(page)

    @router.get(
        "/projects/{project_id}/application-accounts/{application_principal_id}/keys/{key_id}",
        tags=["access"],
        operation_id="getApplicationKey",
        responses=errors,
    )
    async def key(
        project_id: UUID,
        application_principal_id: UUID,
        key_id: UUID,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> ApplicationKeyMetadataResponse:
        async with open_reader() as reader:
            metadata = await reader.get_key(
                access=access,
                project_id=ProjectId(project_id),
                application_principal_id=PrincipalId(application_principal_id),
                key_id=ApplicationKeyId(key_id),
            )
        return ApplicationAccountMapper.key(metadata)

    return router
