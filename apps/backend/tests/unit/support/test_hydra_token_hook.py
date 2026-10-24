import asyncio
from uuid import uuid4

import httpx2
import pytest
from fastapi import FastAPI, HTTPException, Request
from tests.support.hydra_token_hook import create_hydra_token_hook_router


def _app(timeout: float = 10.0) -> FastAPI:
    def require_key(request: Request) -> None:
        if request.headers.get("X-Inframeld-Recovery-Key") != "test-key":
            raise HTTPException(status_code=401)

    app = FastAPI()
    app.include_router(create_hydra_token_hook_router(require_key, gate_timeout_seconds=timeout))
    return app


def _payload(subject: str, grant: str = "refresh_token") -> dict[str, object]:
    return {
        "session": {
            "id_token": {"subject": subject},
            "client_id": "inframeld-cli",
            "private": "token-secret",
        },
        "request": {
            "client_id": "inframeld-cli",
            "grant_types": [grant],
            "payload": {"code": ["code-secret"]},
        },
    }


@pytest.mark.asyncio
async def test_gate_pauses_exactly_one_matching_request_and_observes_no_credentials() -> None:
    subject = str(uuid4())
    key = {"X-Inframeld-Recovery-Key": "test-key"}
    path = f"/hydra/token-plans/{subject}/refresh_token"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app()), base_url="http://hook.test", headers=key
    ) as client:
        assert (await client.put(path)).status_code == 204
        async with asyncio.TaskGroup() as tasks:
            paused = tasks.create_task(
                client.post("/internal/test/hydra/token", json=_payload(subject))
            )
            observed = await client.get(path + "/arrived")
            assert observed.status_code == 200
            assert observed.json() == {
                "subject": subject,
                "client_id": "inframeld-cli",
                "grant_type": "refresh_token",
                "arrivals": 1,
            }
            assert "secret" not in observed.text
            assert not paused.done()
            assert (
                await client.post("/internal/test/hydra/token", json=_payload(subject))
            ).status_code == 204
            assert (await client.post(path + "/release")).status_code == 204
        assert paused.result().status_code == 204
        assert (await client.delete(path)).status_code == 204


@pytest.mark.asyncio
async def test_unrelated_request_passes_without_opening_the_armed_gate() -> None:
    subject = str(uuid4())
    path = f"/hydra/token-plans/{subject}/refresh_token"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app()),
        base_url="http://hook.test",
        headers={"X-Inframeld-Recovery-Key": "test-key"},
    ) as client:
        assert (await client.put(path)).status_code == 204
        assert (
            await client.post("/internal/test/hydra/token", json=_payload(str(uuid4())))
        ).status_code == 204
        assert (
            await client.post(
                "/internal/test/hydra/token", json=_payload(subject, "authorization_code")
            )
        ).status_code == 204
        assert (await client.delete(path)).status_code == 204


@pytest.mark.asyncio
async def test_gate_deadline_denies_the_request_without_retrying_or_exposing_payload() -> None:
    subject = str(uuid4())
    path = f"/hydra/token-plans/{subject}/refresh_token"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(0.01)),
        base_url="http://hook.test",
        headers={"X-Inframeld-Recovery-Key": "test-key"},
    ) as client:
        await client.put(path)
        response = await client.post("/internal/test/hydra/token", json=_payload(subject))
        assert response.status_code == 403
        assert "secret" not in response.text


@pytest.mark.asyncio
async def test_deleting_a_plan_releases_its_waiting_request() -> None:
    subject = str(uuid4())
    path = f"/hydra/token-plans/{subject}/refresh_token"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app()),
        base_url="http://hook.test",
        headers={"X-Inframeld-Recovery-Key": "test-key"},
    ) as client:
        await client.put(path)
        async with asyncio.TaskGroup() as tasks:
            paused = tasks.create_task(
                client.post("/internal/test/hydra/token", json=_payload(subject))
            )
            assert (await client.get(path + "/arrived")).status_code == 200
            assert (await client.delete(path)).status_code == 204
        assert paused.result().status_code == 204


@pytest.mark.asyncio
async def test_cancellation_does_not_leave_the_handler_waiting() -> None:
    subject = str(uuid4())
    path = f"/hydra/token-plans/{subject}/refresh_token"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app()),
        base_url="http://hook.test",
        headers={"X-Inframeld-Recovery-Key": "test-key"},
    ) as client:
        await client.put(path)
        task = asyncio.create_task(
            client.post("/internal/test/hydra/token", json=_payload(subject))
        )
        await client.get(path + "/arrived")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await client.delete(path)).status_code == 204


@pytest.mark.asyncio
async def test_private_test_key_is_required() -> None:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app()), base_url="http://hook.test"
    ) as client:
        assert (
            await client.post("/internal/test/hydra/token", json=_payload(str(uuid4())))
        ).status_code == 401


@pytest.mark.asyncio
async def test_invalid_payload_is_rejected_without_echoing_the_body() -> None:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app()),
        base_url="http://hook.test",
        headers={"X-Inframeld-Recovery-Key": "test-key"},
    ) as client:
        response = await client.post(
            "/internal/test/hydra/token", json={"session": "secret-token-material", "request": {}}
        )
    assert response.status_code == 400
    assert "secret-token-material" not in response.text
