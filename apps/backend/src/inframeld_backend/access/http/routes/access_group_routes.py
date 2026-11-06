from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.commands.create_access_group_command import (
    CreateAccessGroupCommand,
)
from inframeld_backend.access.application.commands.delete_access_group_command import (
    DeleteAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.enums.access_group_collection import AccessGroupCollection
from inframeld_backend.access.application.protocols.access_group_creator import AccessGroupCreator
from inframeld_backend.access.application.protocols.access_group_deleter import AccessGroupDeleter
from inframeld_backend.access.application.protocols.access_group_reader import AccessGroupReader
from inframeld_backend.access.application.protocols.access_group_relationship_changer import (
    AccessGroupRelationshipChanger,
)
from inframeld_backend.access.application.queries.list_access_group_principals_query import (
    ListAccessGroupPrincipalsQuery,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.mappers.access_group_mapper import AccessGroupMapper
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.access_group_creation_request import (
    AccessGroupCreationRequest,
)
from inframeld_backend.access.http.requests.access_group_manager_request import (
    AccessGroupManagerRequest,
)
from inframeld_backend.access.http.requests.access_group_membership_request import (
    AccessGroupMembershipRequest,
)
from inframeld_backend.access.http.responses.access_group_creation_response import (
    AccessGroupCreationResponse,
)
from inframeld_backend.access.http.responses.access_group_deletion_response import (
    AccessGroupDeletionResponse,
)
from inframeld_backend.access.http.responses.access_group_manager_removal_response import (
    AccessGroupManagerRemovalResponse,
)
from inframeld_backend.access.http.responses.access_group_manager_response import (
    AccessGroupManagerResponse,
)
from inframeld_backend.access.http.responses.access_group_membership_removal_response import (
    AccessGroupMembershipRemovalResponse,
)
from inframeld_backend.access.http.responses.access_group_membership_response import (
    AccessGroupMembershipResponse,
)
from inframeld_backend.access.http.responses.access_group_metadata_response import (
    AccessGroupMetadataResponse,
)
from inframeld_backend.access.http.responses.access_group_principals_page_response import (
    AccessGroupPrincipalsPageResponse,
)
from inframeld_backend.access.http.routes.access_group_route import AccessGroupRoute
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
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


def create_access_group_router(
    authenticate: HumanSessionDependency,
    open_creator: Callable[[], AbstractAsyncContextManager[AccessGroupCreator]],
    open_reader: Callable[[], AbstractAsyncContextManager[AccessGroupReader]],
    open_changer: Callable[[], AbstractAsyncContextManager[AccessGroupRelationshipChanger]],
    open_deleter: Callable[[], AbstractAsyncContextManager[AccessGroupDeleter]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=AccessGroupRoute)
    errors = (
        human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(CONFLICT_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM)
    )
    write_errors = (
        errors | problem_responses(for_http_status(413)) | problem_responses(for_http_status(415))
    )
    key_dependency = IdempotencyKeyDependency()

    @router.post(
        "/projects/{project_id}/access-groups",
        tags=["access"],
        operation_id="createAccessGroup",
        status_code=201,
        responses=write_errors,
    )
    async def create(
        project_id: UUID,
        body: AccessGroupCreationRequest,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> AccessGroupCreationResponse:
        project = ProjectId(project_id)
        async with open_creator() as creator:
            result = await creator.create(
                access=access,
                command=CreateAccessGroupCommand(
                    project,
                    body.expected_access_revision,
                    ResourceName(body.name),
                    SubmittedDisplayName(body.display_name),
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.POST, f"/v1/projects/{project_id}/access-groups", key
                ),
            )
        return AccessGroupMapper.creation(result)

    @router.get(
        "/projects/{project_id}/access-groups/resolve",
        tags=["access"],
        operation_id="resolveAccessGroup",
        responses=errors,
    )
    async def resolve(
        project_id: UUID,
        name: Annotated[
            str, Query(min_length=1, max_length=63, pattern="^[a-z](?:[a-z0-9-]*[a-z0-9])?$")
        ],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> AccessGroupMetadataResponse:
        async with open_reader() as reader:
            group = await reader.inspect(
                access=access, project_id=ProjectId(project_id), selector=ResourceName(name)
            )
        return AccessGroupMapper.metadata(group)

    @router.get(
        "/projects/{project_id}/access-groups/{access_group_id}",
        tags=["access"],
        operation_id="getAccessGroup",
        responses=errors,
    )
    async def get(
        project_id: UUID,
        access_group_id: UUID,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> AccessGroupMetadataResponse:
        async with open_reader() as reader:
            group = await reader.inspect(
                access=access,
                project_id=ProjectId(project_id),
                selector=AccessGroupId(access_group_id),
            )
        return AccessGroupMapper.metadata(group)

    @router.get(
        "/projects/{project_id}/access-groups/{access_group_id}/members",
        tags=["access"],
        operation_id="listAccessGroupMembers",
        responses=errors,
    )
    async def list_members(
        project_id: UUID,
        access_group_id: UUID,
        pagination: Annotated[PaginationQuery, Query()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> AccessGroupPrincipalsPageResponse:
        async with open_reader() as reader:
            page = await reader.list_principals(
                access=access,
                query=ListAccessGroupPrincipalsQuery(
                    ProjectId(project_id),
                    AccessGroupId(access_group_id),
                    AccessGroupCollection.MEMBERS,
                    pagination.limit,
                    pagination.cursor,
                ),
            )
        return AccessGroupMapper.page(page)

    @router.get(
        "/projects/{project_id}/access-groups/{access_group_id}/managers",
        tags=["access"],
        operation_id="listAccessGroupManagers",
        responses=errors,
    )
    async def list_managers(
        project_id: UUID,
        access_group_id: UUID,
        pagination: Annotated[PaginationQuery, Query()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> AccessGroupPrincipalsPageResponse:
        async with open_reader() as reader:
            page = await reader.list_principals(
                access=access,
                query=ListAccessGroupPrincipalsQuery(
                    ProjectId(project_id),
                    AccessGroupId(access_group_id),
                    AccessGroupCollection.MANAGERS,
                    pagination.limit,
                    pagination.cursor,
                ),
            )
        return AccessGroupMapper.page(page)

    @router.put(
        "/projects/{project_id}/access-groups/{access_group_id}/members/{principal_id}",
        tags=["access"],
        operation_id="addAccessGroupMember",
        status_code=201,
        responses=write_errors | {200: {"model": AccessGroupMembershipResponse}},
    )
    async def add_member(
        project_id: UUID,
        access_group_id: UUID,
        principal_id: UUID,
        body: AccessGroupMembershipRequest,
        response: Response,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> AccessGroupMembershipResponse:
        async with open_changer() as changer:
            result = await changer.change(
                access=access,
                command=ChangeAccessGroupRelationshipCommand(
                    ProjectId(project_id),
                    AccessGroupId(access_group_id),
                    PrincipalId(principal_id),
                    body.expected_access_revision,
                    AccessGroupChangeKind.ADD_MEMBER,
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.PUT,
                    f"/v1/projects/{project_id}/access-groups/{access_group_id}/members/{principal_id}",
                    key,
                ),
            )
        response.status_code = result.status_code
        return AccessGroupMapper.membership(result)

    @router.delete(
        "/projects/{project_id}/access-groups/{access_group_id}/members/{principal_id}",
        tags=["access"],
        operation_id="removeAccessGroupMember",
        responses=errors,
    )
    async def remove_member(
        project_id: UUID,
        access_group_id: UUID,
        principal_id: UUID,
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
    ) -> AccessGroupMembershipRemovalResponse:
        async with open_changer() as changer:
            result = await changer.change(
                access=access,
                command=ChangeAccessGroupRelationshipCommand(
                    ProjectId(project_id),
                    AccessGroupId(access_group_id),
                    PrincipalId(principal_id),
                    expected_access_revision,
                    AccessGroupChangeKind.REMOVE_MEMBER,
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.DELETE,
                    f"/v1/projects/{project_id}/access-groups/{access_group_id}/members/{principal_id}",
                    key,
                ),
            )
        return AccessGroupMapper.membership_removal(result)

    @router.put(
        "/projects/{project_id}/access-groups/{access_group_id}/managers/{principal_id}",
        tags=["access"],
        operation_id="appointAccessGroupManager",
        status_code=201,
        responses=write_errors | {200: {"model": AccessGroupManagerResponse}},
    )
    async def appoint_manager(
        project_id: UUID,
        access_group_id: UUID,
        principal_id: UUID,
        body: AccessGroupManagerRequest,
        response: Response,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> AccessGroupManagerResponse:
        async with open_changer() as changer:
            result = await changer.change(
                access=access,
                command=ChangeAccessGroupRelationshipCommand(
                    ProjectId(project_id),
                    AccessGroupId(access_group_id),
                    PrincipalId(principal_id),
                    body.expected_access_revision,
                    AccessGroupChangeKind.APPOINT_MANAGER,
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.PUT,
                    f"/v1/projects/{project_id}/access-groups/{access_group_id}/managers/{principal_id}",
                    key,
                ),
            )
        response.status_code = result.status_code
        return AccessGroupMapper.manager(result)

    @router.delete(
        "/projects/{project_id}/access-groups/{access_group_id}/managers/{principal_id}",
        tags=["access"],
        operation_id="removeAccessGroupManager",
        responses=errors,
    )
    async def remove_manager(
        project_id: UUID,
        access_group_id: UUID,
        principal_id: UUID,
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
    ) -> AccessGroupManagerRemovalResponse:
        async with open_changer() as changer:
            result = await changer.change(
                access=access,
                command=ChangeAccessGroupRelationshipCommand(
                    ProjectId(project_id),
                    AccessGroupId(access_group_id),
                    PrincipalId(principal_id),
                    expected_access_revision,
                    AccessGroupChangeKind.REMOVE_MANAGER,
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.DELETE,
                    f"/v1/projects/{project_id}/access-groups/{access_group_id}/managers/{principal_id}",
                    key,
                ),
            )
        return AccessGroupMapper.manager_removal(result)

    @router.delete(
        "/projects/{project_id}/access-groups/{access_group_id}",
        tags=["access"],
        operation_id="deleteAccessGroup",
        responses=errors,
    )
    async def delete(
        project_id: UUID,
        access_group_id: UUID,
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
    ) -> AccessGroupDeletionResponse:
        request_id: object = getattr(request.state, "request_id", None)
        if not isinstance(request_id, RequestId):
            raise RuntimeError("Group deletion requires trusted request correlation.")
        async with open_deleter() as deleter:
            result = await deleter.delete(
                access=access,
                command=DeleteAccessGroupCommand(
                    ProjectId(project_id), AccessGroupId(access_group_id), expected_access_revision
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.DELETE,
                    f"/v1/projects/{project_id}/access-groups/{access_group_id}",
                    key,
                ),
                request_id=request_id,
            )
        return AccessGroupMapper.deletion(result)

    return router
