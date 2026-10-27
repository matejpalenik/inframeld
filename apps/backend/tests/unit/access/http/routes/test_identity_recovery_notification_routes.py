import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import override

import httpx2
import pytest
from fastapi import FastAPI

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_notification_result_dto import (
    IdentityRecoveryNotificationResultDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType as Event,
)
from inframeld_backend.access.application.protocols.identity_recovery_notification_handler import (
    IdentityRecoveryNotificationHandler,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.http.dependencies.recovery_hook_authentication_dependency import (
    RecoveryHookAuthenticationDependency,
)
from inframeld_backend.access.http.middleware.recovery_notification_response_middleware import (
    RecoveryNotificationResponseMiddleware,
)
from inframeld_backend.access.http.routes.identity_recovery_notification_routes import (
    create_recovery_notification_router,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers

KEY = b"current-test-hook-key-32-bytes-long"
OLD = b"retiring-test-hook-key-32-bytes-long"
ADMISSION = {
    "schemaVersion": 2,
    "eventType": Event.RECOVERY_CODE_VERIFIED.value,
    "identityId": "10000000-0000-0000-0000-000000000001",
    "recoveryFlowId": "20000000-0000-0000-0000-000000000001",
    "eventKind": "recovery",
}
PATH = "/internal/v2/identity-recovery"


class Handler(IdentityRecoveryNotificationHandler):
    def __init__(self) -> None:
        self.calls = 0
        self.stall = False
        self.entered = asyncio.Event()
        self.cancelled = False

    @override
    async def admit(self, event: IdentityRecoveryEventDTO) -> IdentityRecoveryNotificationResultDTO:
        self.calls += 1
        self.entered.set()
        if self.stall:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return IdentityRecoveryNotificationResultDTO(
            OperationId("original-operation"), Event.RECOVERY_CODE_VERIFIED
        )

    @override
    async def associate_settings(
        self, evidence: IdentityRecoverySettingsEvidenceDTO
    ) -> IdentityRecoveryNotificationResultDTO | None:
        self.calls += 1
        return None

    @override
    async def record_password_saved(
        self, evidence: IdentityRecoverySettingsEvidenceDTO
    ) -> IdentityRecoveryNotificationResultDTO | None:
        self.calls += 1
        return None


def _app(handler: Handler, *, expired: bool = False, budget: float = 1.0) -> FastAPI:
    app = FastAPI(docs_url=None, openapi_url=None, redoc_url=None)
    register_error_handlers(app)
    app.add_middleware(RecoveryNotificationResponseMiddleware)

    @asynccontextmanager
    async def provider() -> AsyncGenerator[IdentityRecoveryNotificationHandler]:
        yield handler

    app.include_router(
        create_recovery_notification_router(
            RecoveryHookAuthenticationDependency(
                current=KEY,
                retiring=OLD,
                retiring_accept_until=datetime.now(UTC) + timedelta(hours=-1 if expired else 1),
            ),
            provider,
            authority=IdentityAuthority("https://identity.test"),
            request_timeout_seconds=budget,
        )
    )
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [KEY, OLD])
async def test_authenticated_admission_returns_original_acknowledgment(key: bytes) -> None:
    handler = Handler()
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(handler)), base_url="http://private"
    ) as client:
        response = await client.post(
            PATH + "/admit", json=ADMISSION, headers={"X-Inframeld-Recovery-Key": key.decode()}
        )
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert response.status_code == 202
    assert response.json() == {
        "schemaVersion": 2,
        "eventType": Event.RECOVERY_CODE_VERIFIED.value,
        "operationId": "original-operation",
        "recorded": True,
    }
    assert handler.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        [],
        [("Authorization", "Bearer secret")],
        [("X-Inframeld-Recovery-Key", "wrong")],
        [("X-Inframeld-Recovery-Key", KEY.decode()), ("X-Inframeld-Recovery-Key", KEY.decode())],
    ],
)
async def test_authentication_precedes_body_consumption(headers: list[tuple[str, str]]) -> None:
    handler = Handler()
    consumed = False

    async def body() -> AsyncGenerator[bytes]:
        nonlocal consumed
        consumed = True
        yield b"not-json"

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(handler)), base_url="http://private"
    ) as client:
        response = await client.post(PATH + "/admit", content=body(), headers=headers)
    assert response.status_code == 401
    assert not consumed
    assert handler.calls == 0
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_retiring_key_stops_working_at_expiry() -> None:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(Handler(), expired=True)), base_url="http://private"
    ) as client:
        response = await client.post(
            PATH + "/admit", json=ADMISSION, headers={"X-Inframeld-Recovery-Key": OLD.decode()}
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_actual_streamed_size_is_enforced_without_trusting_content_length() -> None:
    handler = Handler()

    async def body() -> AsyncGenerator[bytes]:
        yield b" " * 4096
        yield b" " * 4097

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(handler)), base_url="http://private"
    ) as client:
        response = await client.post(
            PATH + "/admit",
            content=body(),
            headers={
                "X-Inframeld-Recovery-Key": KEY.decode(),
                "Content-Type": "application/json",
                "Content-Length": "1",
            },
        )
    assert response.status_code == 413
    assert handler.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content_type, body, status",
    [
        ("text/plain", b"{}", 415),
        ("application/json", b"{}", 422),
        ("application/json", b'{"schemaVersion":2,"schemaVersion":2}', 422),
        ("application/json", b"secret", 422),
    ],
)
async def test_bad_envelopes_never_reach_the_service(
    content_type: str, body: bytes, status: int
) -> None:
    handler = Handler()
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(handler)), base_url="http://private"
    ) as client:
        response = await client.post(
            PATH + "/admit",
            content=body,
            headers={"X-Inframeld-Recovery-Key": KEY.decode(), "Content-Type": content_type},
        )
    assert response.status_code == status
    assert handler.calls == 0
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_deadline_cancels_unfinished_work_and_returns_unavailable() -> None:
    handler = Handler()
    handler.stall = True
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(handler, budget=0.02)), base_url="http://private"
    ) as client:
        response = await client.post(
            PATH + "/admit", json=ADMISSION, headers={"X-Inframeld-Recovery-Key": KEY.decode()}
        )
    assert response.status_code == 503
    assert handler.cancelled
    assert handler.calls == 1


@pytest.mark.asyncio
async def test_caller_cancellation_propagates() -> None:
    handler = Handler()
    handler.stall = True
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(handler)), base_url="http://private"
    ) as client:
        task = asyncio.create_task(
            client.post(
                PATH + "/admit", json=ADMISSION, headers={"X-Inframeld-Recovery-Key": KEY.decode()}
            )
        )
        await asyncio.wait_for(handler.entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert handler.cancelled


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route, event",
    [
        ("settings", Event.SETTINGS_FLOW_ASSOCIATED),
        ("password-saved", Event.PASSWORD_SETTINGS_SAVED),
    ],
)
async def test_unassociated_settings_have_no_recovery_acknowledgment(
    route: str, event: Event
) -> None:
    body = {
        "schemaVersion": 2,
        "eventType": event.value,
        "identityId": ADMISSION["identityId"],
        "settingsFlowId": ADMISSION["recoveryFlowId"],
        "sessionId": ADMISSION["recoveryFlowId"],
        "sourceRecoveryFlowId": None,
    }
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(Handler())), base_url="http://private"
    ) as client:
        response = await client.post(
            PATH + "/" + route,
            content=json.dumps(body),
            headers={"X-Inframeld-Recovery-Key": KEY.decode(), "Content-Type": "application/json"},
        )
    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"


@pytest.mark.asyncio
async def test_unconfigured_native_event_kind_is_rejected_before_admission() -> None:
    handler = Handler()
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(handler)), base_url="http://private"
    ) as client:
        response = await client.post(
            PATH + "/admit",
            json=ADMISSION | {"eventKind": "password-reset"},
            headers={"X-Inframeld-Recovery-Key": KEY.decode()},
        )
    assert response.status_code == 422
    assert handler.calls == 0


@pytest.mark.asyncio
async def test_body_receipt_is_inside_the_request_deadline() -> None:
    handler = Handler()
    closed = False

    async def body() -> AsyncGenerator[bytes]:
        nonlocal closed
        try:
            yield b"{"
            await asyncio.Event().wait()
        finally:
            closed = True

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(handler, budget=0.02)), base_url="http://private"
    ) as client:
        response = await client.post(
            PATH + "/admit",
            content=body(),
            headers={"X-Inframeld-Recovery-Key": KEY.decode(), "Content-Type": "application/json"},
        )
    assert response.status_code == 503
    assert closed
    assert handler.calls == 0
