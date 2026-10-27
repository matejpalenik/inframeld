"""Observe real Kratos recovery hooks and native session revocation."""

import asyncio
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import httpx2
import pytest
import pytest_asyncio
from pydantic import SecretStr
from tests.support.integration_services import RECOVERY_HOOKS_URL
from tests.support.kratos_browser import (
    RegisteredHumanDTO,
    WhoamiResponse,
    create_browser,
    register_human,
)
from tests.support.kratos_recovery import (
    RecoveryFlowResponse,
    redeem_recovery_code,
    request_recovery_code,
    wait_for_recovery_code,
)
from tests.support.kratos_recovery_hooks import (
    TEST_RECOVERY_KEY,
    MockRecoveryPlanRequest,
    MockRecoverySnapshotResponse,
    RecoveryPhase,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires the private Kratos integration services",
)


@dataclass(frozen=True, slots=True)
class RecoveryScenarioDTO:
    """Group the clients and flow owned by the scenario fixture."""

    human: RegisteredHumanDTO
    flow: RecoveryFlowResponse
    code: SecretStr = field(repr=False)
    old_browser: httpx2.AsyncClient
    recovering_browser: httpx2.AsyncClient
    callbacks: httpx2.AsyncClient


@pytest_asyncio.fixture
async def scenario() -> AsyncGenerator[RecoveryScenarioDTO]:
    async with (
        create_browser() as old_browser,
        create_browser() as recovering_browser,
        httpx2.AsyncClient(
            base_url=RECOVERY_HOOKS_URL,
            headers={"X-Inframeld-Recovery-Key": TEST_RECOVERY_KEY.get_secret_value()},
            timeout=2.0,
            trust_env=False,
        ) as callbacks,
    ):
        human = await register_human(old_browser)
        flow = await request_recovery_code(recovering_browser, human.email)
        code = await wait_for_recovery_code(human.email)
        yield RecoveryScenarioDTO(human, flow, code, old_browser, recovering_browser, callbacks)


async def _configure(scenario: RecoveryScenarioDTO, plan: MockRecoveryPlanRequest) -> None:
    response = await scenario.callbacks.put(
        f"/plans/{scenario.flow.id}", json=plan.model_dump(mode="json")
    )
    assert response.status_code == 204, "Could not configure the callback probe."


async def _snapshot(scenario: RecoveryScenarioDTO) -> MockRecoverySnapshotResponse:
    response = await scenario.callbacks.get(f"/observations/{scenario.flow.id}")
    assert response.status_code == 200, "Could not inspect the callback probe."
    return MockRecoverySnapshotResponse.model_validate_json(response.text)


async def _release(scenario: RecoveryScenarioDTO, phase: RecoveryPhase) -> None:
    response = await scenario.callbacks.post(f"/plans/{scenario.flow.id}/release/{phase}")
    assert response.status_code == 204, "Could not release the callback probe."


async def _wait_for_phase(
    scenario: RecoveryScenarioDTO, phase: RecoveryPhase
) -> MockRecoverySnapshotResponse:
    async with asyncio.timeout(5.0):
        while True:
            snapshot = await _snapshot(scenario)
            if any(event.phase == phase for event in snapshot.received):
                return snapshot
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_requesting_recovery_email_does_not_run_cleanup_hooks(
    scenario: RecoveryScenarioDTO,
) -> None:
    """Knowing an email address must not let someone sign its owner out."""
    snapshot = await _snapshot(scenario)
    assert snapshot.received == []
    assert snapshot.acknowledged == []
    assert (await scenario.old_browser.get("/sessions/whoami")).status_code == 200
    assert (await scenario.recovering_browser.get("/sessions/whoami")).status_code == 401


@pytest.mark.asyncio
async def test_invalid_recovery_code_does_not_run_cleanup_hooks(
    scenario: RecoveryScenarioDTO,
) -> None:
    """Cleanup starts only after the recovery code has been verified."""
    await redeem_recovery_code(
        scenario.recovering_browser, scenario.flow, SecretStr("not-a-valid-code")
    )
    assert (await _snapshot(scenario)).received == []
    assert (await scenario.old_browser.get("/sessions/whoami")).status_code == 200
    assert (await scenario.recovering_browser.get("/sessions/whoami")).status_code == 401


@pytest.mark.asyncio
async def test_native_revocation_runs_between_admission_and_completion(
    scenario: RecoveryScenarioDTO,
) -> None:
    """Observe each boundary while the real recovery request is still running."""
    await _configure(scenario, MockRecoveryPlanRequest(pause=True))
    submitted = asyncio.create_task(
        redeem_recovery_code(scenario.recovering_browser, scenario.flow, scenario.code)
    )
    try:
        admitted = await _wait_for_phase(scenario, "admit")
        assert [event.phase for event in admitted.received] == ["admit"]
        assert admitted.acknowledged == []
        assert (await scenario.old_browser.get("/sessions/whoami")).status_code == 200

        await _release(scenario, "admit")
        completing = await _wait_for_phase(scenario, "complete")
        assert [event.phase for event in completing.received] == ["admit", "complete"]
        assert completing.acknowledged == ["admit"]
        assert (await scenario.old_browser.get("/sessions/whoami")).status_code == 401

        for event in completing.received:
            assert event.flow_id == scenario.flow.id
            assert str(event.identity_id) == scenario.human.subject.value
            assert event.event_kind == "recovery"

        await _release(scenario, "complete")
        completed = await submitted
        assert completed.status_code in {302, 303}, "Recovery did not finish."

        whoami = await scenario.recovering_browser.get("/sessions/whoami")
        assert whoami.status_code == 200, "The legitimate recovery session was lost."
        identity = WhoamiResponse.model_validate_json(whoami.text).identity
        assert str(identity.id) == scenario.human.subject.value
        assert (await _snapshot(scenario)).acknowledged == ["admit", "complete"]
    finally:
        try:
            await _release(scenario, "admit")
            await _release(scenario, "complete")
        finally:
            if not submitted.done():
                submitted.cancel()
            await asyncio.gather(submitted, return_exceptions=True)


@pytest.mark.asyncio
async def test_failed_admission_prevents_revocation_and_new_session(
    scenario: RecoveryScenarioDTO,
) -> None:
    """Kratos must stop before cleanup if admission was not acknowledged."""
    await _configure(scenario, MockRecoveryPlanRequest(reject_phase="admit"))
    await redeem_recovery_code(scenario.recovering_browser, scenario.flow, scenario.code)

    snapshot = await _snapshot(scenario)
    assert [event.phase for event in snapshot.received] == ["admit"]
    assert snapshot.acknowledged == []
    assert (await scenario.old_browser.get("/sessions/whoami")).status_code == 200
    assert (await scenario.recovering_browser.get("/sessions/whoami")).status_code == 401
    assert scenario.recovering_browser.cookies.get("ory_kratos_session") is None


@pytest.mark.asyncio
async def test_failed_completion_does_not_undo_native_revocation(
    scenario: RecoveryScenarioDTO,
) -> None:
    """Native cleanup may succeed even though completion remains unconfirmed."""
    await _configure(scenario, MockRecoveryPlanRequest(reject_phase="complete"))
    await redeem_recovery_code(scenario.recovering_browser, scenario.flow, scenario.code)

    snapshot = await _snapshot(scenario)
    assert [event.phase for event in snapshot.received] == ["admit", "complete"]
    assert snapshot.acknowledged == ["admit"]
    assert (await scenario.old_browser.get("/sessions/whoami")).status_code == 401
    assert (await scenario.recovering_browser.get("/sessions/whoami")).status_code == 401
    assert scenario.recovering_browser.cookies.get("ory_kratos_session") is None
