import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated, override
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.human_admitter import HumanAdmitter
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.mappers.human_admission_mapper import HumanAdmissionMapper
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.human_admission_request import HumanAdmissionRequest
from inframeld_backend.access.http.responses.human_admission_response import HumanAdmissionResponse
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
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


class _HumanAdmissionRoute(APIRoute):
    """Bound admission input before parsing and keep all outcomes non-cacheable."""

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

        if scope["method"] != "POST":
            await super().handle(scope, receive, private_response)
            return
        request = Request(scope, receive)
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


def create_human_admission_router(
    authenticate: HumanSessionDependency,
    open_admitter: Callable[[], AbstractAsyncContextManager[HumanAdmitter]],
) -> APIRouter:
    router = APIRouter(prefix="/v1", route_class=_HumanAdmissionRoute)
    key_dependency = IdempotencyKeyDependency()

    @router.post(
        "/organizations/{organization_id}/human-admissions",
        status_code=201,
        tags=["access"],
        operation_id="admitHuman",
        responses={200: {"model": HumanAdmissionResponse, "description": "Already admitted."}}
        | human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(CONFLICT_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM)
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def admit(
        organization_id: UUID,
        body: HumanAdmissionRequest,
        response: Response,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> HumanAdmissionResponse:
        async with open_admitter() as service:
            result = await service.admit(
                access=access,
                command=HumanAdmissionMapper.command(organization_id, body),
                context=HumanAdmissionMapper.context(organization_id, key),
            )
        response.status_code = 201 if result.changed else 200
        return HumanAdmissionMapper.response(result)

    return router
