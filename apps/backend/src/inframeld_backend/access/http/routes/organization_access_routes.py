from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated

from fastapi import APIRouter, Depends

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.my_organization_access_reader import (
    MyOrganizationAccessReader,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.mappers.organization_access_mapper import (
    OrganizationAccessMapper,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.responses.my_organization_access_response import (
    MyOrganizationAccessResponse,
)
from inframeld_backend.access.http.routes.project_creation_route import ProjectCreationRoute
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
)
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses


def create_organization_access_router(
    authenticate: HumanSessionDependency,
    open_reader: Callable[[], AbstractAsyncContextManager[MyOrganizationAccessReader]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=ProjectCreationRoute)

    @router.get(
        "/my-organization-access",
        tags=["access"],
        operation_id="getMyOrganizationAccess",
        responses=human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM),
    )
    async def own(
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> MyOrganizationAccessResponse:
        async with open_reader() as service:
            result = await service.read(access=access)
        return OrganizationAccessMapper.response(result)

    return router
