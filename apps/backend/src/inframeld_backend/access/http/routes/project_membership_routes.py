import json
from typing import Annotated, override
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.project_membership_change_service_factory import (
    ProjectMembershipChangeServiceFactory,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.mappers.project_membership_mapper import ProjectMembershipMapper
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.project_membership_request import (
    ProjectMembershipRequest,
)
from inframeld_backend.access.http.responses.project_membership_removal_response import (
    ProjectMembershipRemovalResponse,
)
from inframeld_backend.access.http.responses.project_membership_response import (
    ProjectMembershipResponse,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
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


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON fields so the submitted request has one unambiguous meaning."""
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("Duplicate JSON field.")
        values[key] = value
    return values


def _reject_constant(_value: str) -> object:
    """Reject non-finite JSON constants before mapping the submitted request."""
    raise ValueError("Invalid JSON constant.")


class _ProjectMembershipRoute(APIRoute):
    """Bound PUT JSON and keep DELETE revision solely in its scalar query."""

    @override
    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def private_response(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"cache-control"
                ]
                message = {**message, "headers": headers + [(b"cache-control", b"no-store")]}
            await send(message)

        request = Request(scope, receive)
        method = scope["method"]
        if method == "DELETE":
            invalid = any(
                key != "expectedAccessRevision" or len(request.query_params.getlist(key)) != 1
                for key in request.query_params
            )
            revision = request.query_params.get("expectedAccessRevision")
            if revision is not None and (
                not revision.isascii()
                or not revision.isdecimal()
                or len(revision) > 19
                or (len(revision) > 1 and revision.startswith("0"))
            ):
                invalid = True
            if not invalid:
                async for chunk in request.stream():
                    if chunk:
                        invalid = True
                        break
            if invalid:
                await build_problem_response(request, INVALID_INPUT_PROBLEM)(
                    scope, receive, private_response
                )
                return
            await super().handle(scope, receive, private_response)
            return
        if method != "PUT":
            await super().handle(scope, receive, private_response)
            return
        if request.query_params:
            await build_problem_response(request, INVALID_INPUT_PROBLEM)(
                scope, receive, private_response
            )
            return
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            await build_problem_response(request, for_http_status(415))(
                scope, receive, private_response
            )
            return
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 32768:
                await build_problem_response(request, for_http_status(413))(
                    scope, receive, private_response
                )
                return
            body.extend(chunk)
        try:
            value: object = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object.")
        except (ValueError, RecursionError):
            await build_problem_response(request, INVALID_INPUT_PROBLEM)(
                scope, receive, private_response
            )
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await super().handle(scope, replay, private_response)


def create_project_membership_router(
    authenticate: HumanSessionDependency,
    membership_service_factory: ProjectMembershipChangeServiceFactory,
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=_ProjectMembershipRoute)
    key_dependency = IdempotencyKeyDependency()
    errors = (
        human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(CONFLICT_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM)
    )

    @router.put(
        "/projects/{project_id}/members/{principal_id}",
        tags=["access"],
        operation_id="addProjectMember",
        status_code=201,
        responses={200: {"model": ProjectMembershipResponse, "description": "Already a member."}}
        | errors
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def add(
        project_id: UUID,
        principal_id: UUID,
        body: ProjectMembershipRequest,
        response: Response,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> ProjectMembershipResponse:
        async with membership_service_factory.open() as service:
            result = await service.add_member(
                access=access,
                command=ProjectMembershipMapper.add_command(project_id, principal_id, body),
                context=ProjectMembershipMapper.context(
                    project_id, principal_id, HttpMethod.PUT, key
                ),
            )
        response.status_code = result.status_code
        return ProjectMembershipMapper.add_response(result)

    @router.delete(
        "/projects/{project_id}/members/{principal_id}",
        tags=["access"],
        operation_id="removeProjectMember",
        responses=errors,
    )
    async def remove(
        project_id: UUID,
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
    ) -> ProjectMembershipRemovalResponse:
        async with membership_service_factory.open() as service:
            result = await service.remove_member(
                access=access,
                command=ProjectMembershipMapper.remove_command(
                    project_id, principal_id, expected_access_revision
                ),
                context=ProjectMembershipMapper.context(
                    project_id, principal_id, HttpMethod.DELETE, key
                ),
            )
        return ProjectMembershipMapper.remove_response(result)

    return router
