import asyncio
from contextlib import suppress
from ipaddress import IPv4Address, IPv6Address
from json import dumps, loads
from math import isfinite
from re import fullmatch
from ssl import CERT_REQUIRED, SSLContext
from time import monotonic
from typing import cast, override

import httpcore
import httpx

from inframeld_backend.access.application.value_objects.provider_credential_value import (
    ProviderCredentialValue,
)
from inframeld_backend.shared.application.dtos.embedding_dispatch_result_dto import (
    EmbeddingDispatchResultDTO,
)
from inframeld_backend.shared.application.enums.spending_observation_kind import (
    SpendingObservationKind,
)


class BoundEmbeddingHttpTransport(httpx.AsyncBaseTransport):
    """Constrain the SDK to one exact TLS request over the reviewed numerical route."""

    def __init__(
        self,
        *,
        base_url: str,
        address: IPv4Address | IPv6Address,
        tls: SSLContext,
        model: str,
        tokens: tuple[int, ...],
        dimensions: int,
        credential: ProviderCredentialValue,
        dispatch_deadline: float,
    ) -> None:
        self._endpoint = httpx.URL(f"{base_url.rstrip('/')}/embeddings")
        if (
            self._endpoint.scheme != "https"
            or tls.verify_mode != CERT_REQUIRED
            or not tls.check_hostname
        ):
            raise ValueError("Embedding transport requires verified HTTPS.")
        if not address.is_loopback:
            raise ValueError("The qualified embedding route requires an explicit loopback address.")
        self._route = self._endpoint.copy_with(host=str(address))
        self._host_header = self._endpoint.netloc.decode("ascii")
        self._body = dumps(
            {
                "model": model,
                "input": [list(tokens)],
                "encoding_format": "float",
                "dimensions": dimensions,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        self._credential = credential
        self._model = model
        self._expected_tokens = len(tokens)
        self._dimensions = dimensions
        self._dispatch_deadline = dispatch_deadline
        self._delegate = httpx.AsyncHTTPTransport(
            verify=tls,
            trust_env=False,
            proxy=None,
            retries=0,
            http2=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
        )
        self._entered = False
        self.not_sent = False
        self.response_status: int | None = None
        self.result: EmbeddingDispatchResultDTO | None = None

    @override
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._entered or request.method != "POST" or request.url != self._endpoint:
            raise httpx.RequestError(
                "The SDK changed the original embedding route.", request=request
            )
        self._entered = True

        body = await request.aread()
        if len(body) > 128 * 1024 or not self._matches_body(body):
            raise httpx.RequestError(
                "The SDK changed the original embedding input.", request=request
            )

        # Reconstruct the complete outbound headers. The SDK can import ambient headers.
        outbound = httpx.Request(
            "POST",
            self._route,
            headers={
                "Host": self._host_header,
                "Authorization": f"Bearer {self._credential.value}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
            content=self._body,
            extensions={
                "timeout": request.extensions["timeout"],
                "sni_hostname": self._endpoint.host,
            },
        )
        received = await self._dispatch(outbound)
        self.response_status = received.status_code
        try:
            if received.status_code != 200:
                return httpx.Response(
                    received.status_code,
                    request=request,
                    json={"error": {"message": "Provider rejected the embedding call."}},
                )
            if received.headers.get("content-encoding", "identity") != "identity":
                raise httpx.ReadError("The embedding response used unsupported encoding.")
            buffer = bytearray()
            async for chunk in received.aiter_raw():
                if len(buffer) + len(chunk) > 128 * 1024:
                    raise httpx.ReadError("The embedding response exceeded the supported limit.")
                buffer.extend(chunk)
            try:
                vector = self._vector(buffer)
            except (ValueError, OverflowError, RecursionError):
                raise httpx.ReadError("The embedding response lacks qualified evidence.") from None
            reference = received.headers.get("x-request-id")
            if reference is not None and (
                self._credential.value in reference
                or fullmatch(r"[A-Za-z0-9._:-]{1,128}", reference) is None
            ):
                reference = None
            self.result = EmbeddingDispatchResultDTO(
                SpendingObservationKind.USAGE, vector, self._expected_tokens, reference, 200
            )
            # Only validated fields enter the SDK. Provider headers and its body are never passed on.
            return httpx.Response(
                200,
                request=request,
                json={
                    "object": "list",
                    "model": self._model,
                    "data": [{"object": "embedding", "index": 0, "embedding": vector}],
                    "usage": {
                        "prompt_tokens": self._expected_tokens,
                        "total_tokens": self._expected_tokens,
                    },
                },
            )

        finally:
            await received.aclose()

    async def _dispatch(self, request: httpx.Request) -> httpx.Response:
        remaining = self._dispatch_deadline - monotonic()
        if remaining <= 0:
            self.not_sent = True
            raise httpx.ConnectTimeout("The original lease expired before transport entry.")

        deadline = asyncio.timeout(remaining)
        connecting = False
        connection_failed = False
        possibly_written = False
        tcp_stream: httpcore.AsyncNetworkStream | None = None

        async def trace(event: str, info: dict[str, object]) -> None:
            nonlocal connecting, connection_failed, possibly_written, tcp_stream
            match event:
                case "connection.connect_tcp.started" | "connection.start_tls.started":
                    connecting = True
                case "connection.connect_tcp.complete":
                    stream = info.get("return_value")
                    if isinstance(stream, httpcore.AsyncNetworkStream):
                        tcp_stream = stream
                case "connection.start_tls.complete":
                    tcp_stream = None
                case "connection.connect_tcp.failed" | "connection.start_tls.failed":
                    connection_failed = True
                case "http11.send_request_headers.started":
                    if monotonic() >= self._dispatch_deadline:
                        self.not_sent = True
                        raise httpx.ConnectTimeout("The original lease expired before HTTP write.")
                    possibly_written = True
                case "http11.send_request_headers.complete":
                    if deadline.expired() or monotonic() >= self._dispatch_deadline:
                        raise httpx.WriteTimeout("The original lease expired during HTTP write.")
                    deadline.reschedule(None)
                case _:
                    pass

        request.extensions["trace"] = trace
        try:
            async with deadline:
                return await self._delegate.handle_async_request(request)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            self.not_sent = self.not_sent or (connection_failed and not possibly_written)
            raise
        except TimeoutError:
            self.not_sent = deadline.expired() and connecting and not possibly_written
            raise
        finally:
            # HTTPcore has no connection to close if the timer cancels its TLS setup.
            if tcp_stream is not None:
                with suppress(OSError):
                    await tcp_stream.aclose()

    def _vector(self, body: bytearray) -> tuple[float, ...]:
        payload = self._object(loads(body, object_pairs_hook=self._unique_object))
        usage = self._object(payload.get("usage"))
        data = self._array(payload.get("data"))
        prompt, total = usage.get("prompt_tokens"), usage.get("total_tokens")
        if (
            payload.get("object") != "list"
            or payload.get("model") != self._model
            or type(prompt) is not int
            or type(total) is not int
            or prompt != self._expected_tokens
            or total != prompt
            or len(data) != 1
        ):
            raise ValueError("The provider response has the wrong usage or selection.")
        entry = self._object(data[0])
        index = entry.get("index")
        values = self._array(entry.get("embedding"))
        if (
            entry.get("object") != "embedding"
            or type(index) is not int
            or index != 0
            or len(values) != self._dimensions
        ):
            raise ValueError("The provider response has the wrong embedding shape.")
        vector: list[float] = []
        for value in values:
            if type(value) not in (int, float):
                raise ValueError("The provider vector contains a nonnumeric value.")
            number = float(cast(int | float, value))
            if not isfinite(number):
                raise ValueError("The provider vector contains a nonfinite value.")
            vector.append(number)
        return tuple(vector)

    @staticmethod
    def _object(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise ValueError("The provider response is not a bounded JSON object.")
        return cast(dict[str, object], value)

    @staticmethod
    def _array(value: object) -> list[object]:
        if not isinstance(value, list):
            raise ValueError("The provider response is not a bounded JSON array.")
        return cast(list[object], value)

    @staticmethod
    def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value = dict(pairs)
        if len(value) != len(pairs):
            raise ValueError("The provider response repeated a JSON property.")
        return value

    def _matches_body(self, body: bytes) -> bool:
        try:
            return (
                dumps(loads(body), separators=(",", ":"), sort_keys=True, allow_nan=False).encode()
                == self._body
            )
        except (ValueError, RecursionError):
            return False

    @override
    async def aclose(self) -> None:
        await self._delegate.aclose()
