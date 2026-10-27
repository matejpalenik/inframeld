import asyncio

import pytest
from starlette.types import Message, Receive, Scope, Send

from inframeld_backend.access.http.middleware.recovery_notification_response_middleware import (
    RecoveryNotificationResponseMiddleware,
)


async def _receive() -> Message:
    return {"type": "http.disconnect"}


@pytest.mark.asyncio
async def test_response_headers_change_without_buffering_streamed_body() -> None:
    first_chunk = asyncio.Event()
    continue_body = asyncio.Event()
    messages: list[Message] = []

    async def stream(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 202,
                "headers": [
                    (b"Cache-Control", b"public"),
                    (b"cache-control", b"max-age=30"),
                    (b"Pragma", b"cache"),
                    (b"x-result", b"accepted"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        first_chunk.set()
        await continue_body.wait()
        await send({"type": "http.response.body", "body": b"second", "more_body": False})

    async def capture(message: Message) -> None:
        messages.append(message)

    task = asyncio.create_task(
        RecoveryNotificationResponseMiddleware(stream)({"type": "http"}, _receive, capture)
    )
    try:
        await asyncio.wait_for(first_chunk.wait(), 1)
        assert messages[0] == {
            "type": "http.response.start",
            "status": 202,
            "headers": [
                (b"x-result", b"accepted"),
                (b"cache-control", b"no-store"),
                (b"pragma", b"no-cache"),
            ],
        }
        assert messages[1]["body"] == b"first" and messages[1]["more_body"]
        continue_body.set()
        await asyncio.wait_for(task, 1)
        assert messages[2] == {"type": "http.response.body", "body": b"second", "more_body": False}
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
async def test_non_http_scopes_pass_through(scope_type: str) -> None:
    scope: Scope = {"type": scope_type}
    message: Message = {"type": "websocket.close", "code": 1000}
    messages: list[Message] = []

    async def application(actual: Scope, receive: Receive, send: Send) -> None:
        assert actual is scope and receive is _receive
        await send(message)

    async def capture(actual: Message) -> None:
        messages.append(actual)

    await RecoveryNotificationResponseMiddleware(application)(scope, _receive, capture)
    assert messages == [message]
    assert messages[0] is message


@pytest.mark.asyncio
async def test_cancellation_reaches_streaming_application() -> None:
    entered = asyncio.Event()
    cancelled = False

    async def application(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal cancelled
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True

    async def discard(_message: Message) -> None:
        pass

    task = asyncio.create_task(
        RecoveryNotificationResponseMiddleware(application)({"type": "http"}, _receive, discard)
    )
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
