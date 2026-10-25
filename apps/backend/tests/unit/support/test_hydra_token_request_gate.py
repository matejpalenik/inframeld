import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import override

import httpx2
import pytest
from tests.support.hydra_token_request_gate import HydraTokenRequestGate, TokenRequestPhase
from tests.support.integration_services import HYDRA_PUBLIC_URL


class MockResponseStream(httpx2.AsyncByteStream):
    def __init__(self, *, fail: bool = False) -> None:
        self.read = False
        self.closed = False
        self.fail = fail

    @override
    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.read = True
        if self.fail:
            raise httpx2.ReadError("Test read failed.")
        yield b"protected-response"

    @override
    async def aclose(self) -> None:
        self.closed = True


class MockTransport(httpx2.AsyncBaseTransport):
    def __init__(self, *, fail: bool = False, stream_fails: bool = False) -> None:
        self.requests: list[httpx2.Request] = []
        self.close_calls = 0
        self.fail = fail
        self.status_code = 200
        self.stream = MockResponseStream(fail=stream_fails)

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.fail:
            raise httpx2.ConnectError("Test connection failed.")
        return httpx2.Response(self.status_code, stream=self.stream)

    @override
    async def aclose(self) -> None:
        self.close_calls += 1


def _token_request() -> httpx2.Request:
    return httpx2.Request("POST", f"{HYDRA_PUBLIC_URL}/oauth2/token")


@asynccontextmanager
async def _pending_request(
    gate: HydraTokenRequestGate,
) -> AsyncGenerator[asyncio.Task[httpx2.Response]]:
    task = asyncio.create_task(gate.handle_async_request(_token_request()))
    try:
        yield task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await gate.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["before_request", "after_response"])
async def test_gate_pauses_the_selected_boundary_and_forwards_only_once(
    phase: TokenRequestPhase,
) -> None:
    """A received response is fully read before cleanup can begin behind the gate."""
    transport = MockTransport()
    gate = HydraTokenRequestGate(transport)
    gate.arm(phase)
    async with _pending_request(gate) as task:
        await gate.wait_until_paused()
        assert not task.done()
        assert len(transport.requests) == (0 if phase == "before_request" else 1)
        assert transport.stream.read == (phase == "after_response")
        assert transport.stream.closed == (phase == "after_response")
        gate.release()
        response = await task
        assert await response.aread() == b"protected-response"
        assert len(transport.requests) == 1
        following = await gate.handle_async_request(_token_request())
        await following.aclose()
        assert len(transport.requests) == 2
    assert transport.close_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("GET", f"{HYDRA_PUBLIC_URL}/oauth2/token"),
        ("POST", f"{HYDRA_PUBLIC_URL}/oauth2/introspect"),
        ("POST", "http://different-provider.test/oauth2/token"),
        ("POST", "http://hydra:4445/oauth2/token"),
    ],
)
async def test_unrelated_requests_do_not_consume_the_armed_gate(method: str, url: str) -> None:
    transport = MockTransport()
    gate = HydraTokenRequestGate(transport)
    gate.arm("before_request")
    response = await gate.handle_async_request(httpx2.Request(method, url))
    await response.aclose()
    async with _pending_request(gate) as task:
        await gate.wait_until_paused()
        assert len(transport.requests) == 1
        gate.release()
        await (await task).aclose()
        assert len(transport.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["before_request", "after_response"])
async def test_unreleased_gate_times_out_without_retrying(phase: TokenRequestPhase) -> None:
    transport = MockTransport()
    gate = HydraTokenRequestGate(transport, timeout_seconds=0.01)
    gate.arm(phase)
    with pytest.raises(TimeoutError):
        await gate.handle_async_request(_token_request())
    assert len(transport.requests) == (0 if phase == "before_request" else 1)
    if phase == "after_response":
        assert transport.stream.closed
    await gate.aclose()
    assert transport.close_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["before_request", "after_response"])
async def test_cancellation_propagates_and_closes_an_observed_response(
    phase: TokenRequestPhase,
) -> None:
    transport = MockTransport()
    gate = HydraTokenRequestGate(transport)
    gate.arm(phase)
    async with _pending_request(gate) as task:
        await gate.wait_until_paused()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(transport.requests) == (0 if phase == "before_request" else 1)
        if phase == "after_response":
            assert transport.stream.closed
    assert transport.close_calls == 1


@pytest.mark.asyncio
async def test_waiting_for_a_request_that_never_arrives_is_bounded() -> None:
    gate = HydraTokenRequestGate(MockTransport(), timeout_seconds=0.01)
    gate.arm("before_request")
    with pytest.raises(TimeoutError):
        await gate.wait_until_paused()
    await gate.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream_fails", [False, True])
async def test_provider_failure_is_propagated_without_retry(stream_fails: bool) -> None:
    transport = MockTransport(fail=not stream_fails, stream_fails=stream_fails)
    gate = HydraTokenRequestGate(transport)
    gate.arm("after_response")
    with pytest.raises(httpx2.TransportError):
        await gate.handle_async_request(_token_request())
    assert len(transport.requests) == 1
    if stream_fails:
        assert transport.stream.closed
    assert gate.response_status is None
    await gate.aclose()


@pytest.mark.asyncio
async def test_closing_a_paused_gate_does_not_dispatch_the_request() -> None:
    transport = MockTransport()
    gate = HydraTokenRequestGate(transport)
    gate.arm("before_request")
    task = asyncio.create_task(gate.handle_async_request(_token_request()))
    try:
        await gate.wait_until_paused()
        await gate.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            await task
        with pytest.raises(RuntimeError, match="closed"):
            await gate.handle_async_request(_token_request())
        with pytest.raises(RuntimeError, match="closed"):
            gate.arm("before_request")
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await gate.aclose()
    assert not transport.requests
    assert transport.close_calls == 1


@pytest.mark.asyncio
async def test_rearming_an_armed_or_paused_gate_is_rejected() -> None:
    gate = HydraTokenRequestGate(MockTransport())
    gate.arm("before_request")
    with pytest.raises(RuntimeError, match="armed"):
        gate.arm("after_response")
    async with _pending_request(gate) as task:
        await gate.wait_until_paused()
        with pytest.raises(RuntimeError, match="paused"):
            gate.arm("after_response")
        gate.release()
        await (await task).aclose()


@pytest.mark.asyncio
async def test_response_status_is_observed_only_after_reading_and_resets_on_rearm() -> None:
    """A lost-response test must know Hydra returned success before discarding it."""
    transport = MockTransport()
    gate = HydraTokenRequestGate(transport)
    assert gate.response_status is None
    gate.arm("after_response")
    async with _pending_request(gate) as task:
        await gate.wait_until_paused()
        assert gate.response_status == 200
        assert transport.stream.read and transport.stream.closed
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(transport.requests) == 1
        gate.arm("before_request")
        assert gate.response_status is None


@pytest.mark.asyncio
async def test_unrelated_response_does_not_replace_the_observed_token_status() -> None:
    transport = MockTransport()
    gate = HydraTokenRequestGate(transport)
    gate.arm("after_response")
    async with _pending_request(gate) as task:
        await gate.wait_until_paused()
        transport.status_code = 503
        response = await gate.handle_async_request(
            httpx2.Request("GET", f"{HYDRA_PUBLIC_URL}/health/ready")
        )
        await response.aclose()
        assert gate.response_status == 200
        gate.release()
        await (await task).aclose()
