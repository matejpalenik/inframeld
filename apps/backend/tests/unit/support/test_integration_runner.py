import asyncio

import httpx2
import pytest
from tests.support.integration_runner import wait_for_http, wait_for_hydra_signing_keys


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["tls", "unavailable"])
async def test_breach_service_readiness_cannot_accept_tls_failure_or_unavailability(
    failure: str,
) -> None:
    pending = {"password-breaches"}
    attempted = False

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempted
        attempted = True
        if failure == "tls":
            raise httpx2.ConnectError("CERTIFICATE_VERIFY_FAILED", request=request)
        return httpx2.Response(503)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as client:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                await wait_for_http(
                    client,
                    "password-breaches",
                    "https://password-breaches:8443/health/ready",
                    pending,
                )
    assert attempted
    assert pending == {"password-breaches"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first",
    [
        httpx2.Response(503),
        httpx2.Response(200, json={"keys": []}),
        httpx2.Response(200, text="unusable"),
    ],
)
async def test_key_readiness_requires_a_nonempty_native_key_set(first: httpx2.Response) -> None:
    pending = {"hydra-keys"}
    calls = 0

    def handle(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/.well-known/jwks.json"
        assert "hydra-keys" in pending
        timeouts: object = request.extensions["timeout"]
        assert timeouts == {"connect": 30.0, "read": 30.0, "write": 30.0, "pool": 30.0}
        return (
            first
            if calls == 1
            else httpx2.Response(200, json={"keys": [{"kid": "test-key", "kty": "RSA"}]})
        )

    async with (
        httpx2.AsyncClient(transport=httpx2.MockTransport(handle), timeout=2) as client,
        asyncio.timeout(5),
    ):
        await wait_for_hydra_signing_keys(client, "hydra-keys", "http://hydra:4444", pending)
    assert calls == 2
    assert not pending


@pytest.mark.asyncio
async def test_cancelled_key_setup_does_not_claim_readiness() -> None:
    entered = asyncio.Event()
    pending = {"hydra-keys"}

    async def handle(request: httpx2.Request) -> httpx2.Response:
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("The request should be cancelled.")

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle), timeout=2) as client:
        task = asyncio.create_task(
            wait_for_hydra_signing_keys(client, "hydra-keys", "http://hydra:4444", pending)
        )
        try:
            async with asyncio.timeout(5):
                await entered.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert pending == {"hydra-keys"}
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
