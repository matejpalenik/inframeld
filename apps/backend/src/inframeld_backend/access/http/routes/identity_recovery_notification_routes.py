import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import APIRouter
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType,
)
from inframeld_backend.access.application.protocols.identity_recovery_notification_handler import (
    IdentityRecoveryNotificationHandler,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.http.dependencies.recovery_hook_authentication_dependency import (
    RecoveryHookAuthenticationDependency,
)
from inframeld_backend.access.http.mappers.identity_recovery_notification_mapper import (
    IdentityRecoveryNotificationMapper,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)


def create_recovery_notification_router(
    authentication: RecoveryHookAuthenticationDependency,
    open_handler: Callable[[], AbstractAsyncContextManager[IdentityRecoveryNotificationHandler]],
    *,
    authority: IdentityAuthority,
    request_timeout_seconds: float,
    event_kind: IdentityRecoveryEventKind = IdentityRecoveryEventKind.RECOVERY,
) -> APIRouter:
    router = APIRouter(prefix="/internal/v2/identity-recovery")

    async def receive(request: Request, event_type: IdentityRecoveryEvidenceType) -> Response:
        try:
            async with asyncio.timeout(request_timeout_seconds):
                authentication.require(request)

                if (
                    request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    != "application/json"
                ):
                    raise HTTPException(415)

                body = bytearray()

                async for chunk in request.stream():
                    if len(body) + len(chunk) > 8192:
                        raise HTTPException(413)
                    body.extend(chunk)

                event = IdentityRecoveryNotificationMapper.from_json(
                    bytes(body), event_type=event_type, authority=authority
                )

                async with open_handler() as handler:
                    if isinstance(event, IdentityRecoveryEventDTO):
                        if event.event_kind is not event_kind:
                            raise HTTPException(422)

                        result = await handler.admit(event)
                    else:
                        if event_type is IdentityRecoveryEvidenceType.SETTINGS_FLOW_ASSOCIATED:
                            result = await handler.associate_settings(event)
                        else:
                            result = await handler.record_password_saved(event)

                if result is None:
                    return Response(status_code=204)

                response = IdentityRecoveryNotificationMapper.to_response(result)

                return JSONResponse(
                    status_code=202, content=response.model_dump(mode="json", by_alias=True)
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @router.post("/admit")
    async def admit(request: Request) -> Response:
        return await receive(request, IdentityRecoveryEvidenceType.RECOVERY_CODE_VERIFIED)

    @router.post("/settings")
    async def settings(request: Request) -> Response:
        return await receive(request, IdentityRecoveryEvidenceType.SETTINGS_FLOW_ASSOCIATED)

    @router.post("/password-saved")
    async def password_saved(request: Request) -> Response:
        return await receive(request, IdentityRecoveryEvidenceType.PASSWORD_SETTINGS_SAVED)

    return router
