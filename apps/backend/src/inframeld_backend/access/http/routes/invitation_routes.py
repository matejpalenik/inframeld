import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated, override
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.protocols.invitation_activator import InvitationActivator
from inframeld_backend.access.application.protocols.invitation_issuer import InvitationIssuer
from inframeld_backend.access.application.protocols.invitation_previewer import InvitationPreviewer
from inframeld_backend.access.application.protocols.invitation_revoker import InvitationRevoker
from inframeld_backend.access.http.dependencies.invitation_browser_dependency import (
    InvitationBrowserDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.mappers.invitation_mapper import InvitationMapper
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.invitation_activation_request import (
    InvitationActivationRequest,
)
from inframeld_backend.access.http.requests.invitation_issue_request import InvitationIssueRequest
from inframeld_backend.access.http.requests.invitation_preview_request import (
    InvitationPreviewRequest,
)
from inframeld_backend.access.http.requests.invitation_revocation_request import (
    InvitationRevocationRequest,
)
from inframeld_backend.access.http.responses.invitation_activation_response import (
    InvitationActivationResponse,
)
from inframeld_backend.access.http.responses.invitation_issue_response import (
    InvitationIssueResponse,
)
from inframeld_backend.access.http.responses.invitation_preview_response import (
    InvitationPreviewResponse,
)
from inframeld_backend.access.http.responses.invitation_revocation_response import (
    InvitationRevocationResponse,
)
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


class _InvitationRoute(APIRoute):
    """Bound invitation input before parsing and keep all outcomes non-cacheable."""

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
        if request.query_params:
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


def create_invitation_router(
    authenticate: ProductAccessDependency,
    preview_browser: InvitationBrowserDependency,
    activation_browser: InvitationBrowserDependency,
    open_issuer: Callable[[], AbstractAsyncContextManager[InvitationIssuer]],
    open_revoker: Callable[[], AbstractAsyncContextManager[InvitationRevoker]],
    open_previewer: Callable[[], AbstractAsyncContextManager[InvitationPreviewer]],
    open_activator: Callable[[], AbstractAsyncContextManager[InvitationActivator]],
) -> APIRouter:
    router = APIRouter(prefix="/v1/invitations", route_class=_InvitationRoute)
    key_dependency = IdempotencyKeyDependency()
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

    @router.post(
        "", status_code=201, tags=["access"], operation_id="issueInvitation", responses=errors
    )
    async def issue(
        body: InvitationIssueRequest,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> InvitationIssueResponse:
        async with open_issuer() as service:
            result = await service.issue(
                access=access,
                command=InvitationMapper.issue_command(body),
                context=InvitationMapper.context("/v1/invitations", key),
            )
        return InvitationMapper.issue_response(result)

    @router.post(
        "/{invitation_id}/revoke",
        tags=["access"],
        operation_id="revokeInvitation",
        responses=errors,
    )
    async def revoke(
        invitation_id: UUID,
        body: InvitationRevocationRequest,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> InvitationRevocationResponse:
        async with open_revoker() as service:
            result = await service.revoke(
                access=access,
                command=InvitationMapper.revoke_command(invitation_id, body),
                context=InvitationMapper.context(f"/v1/invitations/{invitation_id}/revoke", key),
            )
        return InvitationMapper.revoke_response(result)

    @router.post("/preview", tags=["access"], operation_id="previewInvitation", responses=errors)
    async def preview(
        body: InvitationPreviewRequest,
        proof: Annotated[InvitationBrowserProofDTO, Depends(preview_browser)],
    ) -> InvitationPreviewResponse:
        async with open_previewer() as service:
            result = await service.preview(
                proof=proof, query=InvitationMapper.preview_query(body.invitation_token)
            )
        return InvitationMapper.preview_response(result)

    @router.post("/activate", tags=["access"], operation_id="activateInvitation", responses=errors)
    async def activate(
        body: InvitationActivationRequest,
        proof: Annotated[InvitationBrowserProofDTO, Depends(activation_browser)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> InvitationActivationResponse:
        async with open_activator() as service:
            result = await service.activate(
                proof=proof,
                command=InvitationMapper.activate_command(body.invitation_token),
                context=InvitationMapper.context("/v1/invitations/activate", key),
            )
        return InvitationMapper.activate_response(result)

    return router
