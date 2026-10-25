"""Control one token request at the HTTP boundary without pausing Hydra internally."""

import asyncio
from typing import Literal, override

import httpx2

from tests.support.integration_services import HYDRA_PUBLIC_URL

type TokenRequestPhase = Literal["before_request", "after_response"]


class HydraTokenRequestGate(httpx2.AsyncBaseTransport):
    """Pause one explicitly armed token request and own the wrapped transport.

    The after-response gate reads and closes the real response before pausing.
    The test owns any request task and must cancel and await it before teardown.
    """

    def __init__(
        self, transport: httpx2.AsyncBaseTransport, *, timeout_seconds: float = 10.0
    ) -> None:
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._phase: TokenRequestPhase | None = None
        self._arrived = asyncio.Event()
        self._release = asyncio.Event()
        self._paused = False
        self._closed = False
        self._response_status: int | None = None

    def arm(self, phase: TokenRequestPhase) -> None:
        if self._closed:
            raise RuntimeError("The token request gate is closed.")
        if self._phase is not None:
            raise RuntimeError("The token request gate is already armed.")
        if self._paused:
            raise RuntimeError("The token request gate is paused.")
        self._arrived.clear()
        self._release.clear()
        self._phase = phase
        self._response_status = None

    @property
    def response_status(self) -> int | None:
        """Return the armed token response's status only after its complete body was read."""
        return self._response_status

    async def wait_until_paused(self) -> None:
        async with asyncio.timeout(self._timeout_seconds):
            await self._arrived.wait()

    def release(self) -> None:
        self._release.set()

    async def _pause(self) -> None:
        self._paused = True
        self._arrived.set()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._release.wait()
            if self._closed:
                raise RuntimeError("The token request gate is closed.")
        finally:
            self._paused = False

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        if self._closed:
            raise RuntimeError("The token request gate is closed.")
        target = httpx2.URL(f"{HYDRA_PUBLIC_URL}/oauth2/token")
        matches = request.method == "POST" and (
            request.url.scheme,
            request.url.host,
            request.url.port,
            request.url.path,
        ) == (target.scheme, target.host, target.port, target.path)
        phase = self._phase if matches else None
        if phase is not None:
            self._phase = None
        if phase == "before_request":
            await self._pause()
        response = await self._transport.handle_async_request(request)
        if phase == "after_response":
            try:
                await response.aread()
                self._response_status = response.status_code
                await self._pause()
            except BaseException:
                await response.aclose()
                raise
        return response

    @override
    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            self._phase = None
            self._release.set()
            await self._transport.aclose()
