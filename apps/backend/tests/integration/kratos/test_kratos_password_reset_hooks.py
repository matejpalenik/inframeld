"""Qualify password persistence and session cleanup after real code recovery.

The callback recorder observes provider timing only. These tests do not wire
durable product blocks, Hydra cleanup or a production flow association.
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

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
    submit_password_login,
)
from tests.support.kratos_recovery import (
    redeem_recovery_code,
    request_recovery_code,
    wait_for_recovery_code,
)
from tests.support.kratos_recovery_hooks import (
    TEST_RECOVERY_KEY,
    MockSettingsPlanRequest,
    MockSettingsSnapshotResponse,
    SettingsPhase,
)
from tests.support.kratos_settings import (
    SettingsFlowResponse,
    read_recovery_settings,
    submit_password_settings,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires the private Kratos integration services",
)


class SessionResponse(WhoamiResponse):
    id: UUID


@dataclass(frozen=True, slots=True)
class PasswordResetScenarioDTO:
    human: RegisteredHumanDTO
    recovery_flow_id: UUID
    settings: SettingsFlowResponse
    recovering_browser: httpx2.AsyncClient
    callbacks: httpx2.AsyncClient
    new_password: SecretStr


@pytest_asyncio.fixture
async def scenario() -> AsyncGenerator[PasswordResetScenarioDTO]:
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
        recovery = await request_recovery_code(recovering_browser, human.email)
        code = await wait_for_recovery_code(human.email)
        redeemed = await redeem_recovery_code(recovering_browser, recovery, code)
        settings = await read_recovery_settings(recovering_browser, redeemed)
        assert str(settings.identity.id) == human.subject.value
        assert (await old_browser.get("/sessions/whoami")).status_code == 401
        yield PasswordResetScenarioDTO(
            human=human,
            recovery_flow_id=recovery.id,
            settings=settings,
            recovering_browser=recovering_browser,
            callbacks=callbacks,
            new_password=SecretStr(f"ReplacementPassphrase-{uuid4().hex}!"),
        )


async def _configure(scenario: PasswordResetScenarioDTO, plan: MockSettingsPlanRequest) -> None:
    response = await scenario.callbacks.put(
        f"/settings/plans/{scenario.settings.id}", json=plan.model_dump(mode="json")
    )
    assert response.status_code == 204, "Could not configure the settings callback probe."


async def _snapshot(scenario: PasswordResetScenarioDTO) -> MockSettingsSnapshotResponse:
    response = await scenario.callbacks.get(f"/settings/observations/{scenario.settings.id}")
    assert response.status_code == 200, "Could not read settings callback observations."
    return MockSettingsSnapshotResponse.model_validate_json(response.text)


async def _release(scenario: PasswordResetScenarioDTO, phase: SettingsPhase) -> None:
    response = await scenario.callbacks.post(
        f"/settings/plans/{scenario.settings.id}/release/{phase}"
    )
    assert response.status_code == 204, "Could not release the settings callback probe."


async def _wait_for_phase(
    scenario: PasswordResetScenarioDTO, phase: SettingsPhase
) -> MockSettingsSnapshotResponse:
    async with asyncio.timeout(5.0):
        while True:
            snapshot = await _snapshot(scenario)
            if any(event.phase == phase for event in snapshot.received):
                return snapshot
            await asyncio.sleep(0.05)


async def _assert_password(
    scenario: PasswordResetScenarioDTO, password: SecretStr, *, accepted: bool
) -> None:
    async with create_browser() as browser:
        response = await submit_password_login(
            browser, email=scenario.human.email, password=password
        )
        assert response.status_code == (200 if accepted else 400), "Unexpected login outcome."
        whoami = await browser.get("/sessions/whoami")
        assert whoami.status_code == (200 if accepted else 401), "Unexpected session outcome."
        if accepted:
            identity = WhoamiResponse.model_validate_json(whoami.text).identity
            assert str(identity.id) == scenario.human.subject.value


@pytest.mark.asyncio
async def test_recovery_code_does_not_replace_the_password(
    scenario: PasswordResetScenarioDTO,
) -> None:
    """Alice's old password can still sign in between recovery and password setting."""
    await _assert_password(scenario, SecretStr(scenario.human.password), accepted=True)
    await _assert_password(scenario, scenario.new_password, accepted=False)
    assert (await _snapshot(scenario)).received == []


@pytest.mark.asyncio
async def test_password_change_revokes_sessions_created_after_recovery(
    scenario: PasswordResetScenarioDTO,
) -> None:
    """A login made during the password gap must lose access after settings cleanup."""
    await _configure(scenario, MockSettingsPlanRequest(pause=True))
    original = SessionResponse.model_validate_json(
        (await scenario.recovering_browser.get("/sessions/whoami")).text
    )
    async with create_browser() as intervening_browser:
        submitted = asyncio.create_task(
            submit_password_settings(
                scenario.recovering_browser, scenario.settings, scenario.new_password
            )
        )
        try:
            before = await _wait_for_phase(scenario, "before")
            assert before.acknowledged == []
            await _assert_password(scenario, scenario.new_password, accepted=False)
            login = await submit_password_login(
                intervening_browser,
                email=scenario.human.email,
                password=SecretStr(scenario.human.password),
            )
            assert login.status_code == 200, "Old password stopped working before persistence."
            assert (await intervening_browser.get("/sessions/whoami")).status_code == 200
            await _release(scenario, "before")
            after = await _wait_for_phase(scenario, "after")
            assert after.acknowledged == ["before"]
            assert [event.phase for event in after.received] == ["before", "after"]
            assert (await intervening_browser.get("/sessions/whoami")).status_code == 401
            await _assert_password(scenario, SecretStr(scenario.human.password), accepted=False)
            await _assert_password(scenario, scenario.new_password, accepted=True)
            preserved = await scenario.recovering_browser.get("/sessions/whoami")
            assert preserved.status_code == 200, "The legitimate settings session was lost."
            assert SessionResponse.model_validate_json(preserved.text).id == original.id

            assert scenario.settings.id != scenario.recovery_flow_id
            assert all(event.settings_flow_id == scenario.settings.id for event in after.received)
            assert all(
                str(event.identity_id) == scenario.human.subject.value for event in after.received
            )
            assert after.received[0].session_id is None
            assert after.received[1].session_id == original.id

            await _release(scenario, "after")
            completed = await submitted
            assert completed.status_code == 200, "Password setting did not finish."
            settings = SettingsFlowResponse.model_validate_json(completed.text)
            assert settings.id == scenario.settings.id
            assert settings.state == "success"
            assert (await _snapshot(scenario)).acknowledged == ["before", "after"]
        finally:
            try:
                await _release(scenario, "before")
                await _release(scenario, "after")
            finally:
                if not submitted.done():
                    submitted.cancel()
                await asyncio.gather(submitted, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(("phase", "expected_status"), [("before", 400), ("after", 502)])
async def test_hook_failure_has_phase_specific_persistence(
    scenario: PasswordResetScenarioDTO, phase: SettingsPhase, expected_status: int
) -> None:
    """A post-save callback failure cannot undo Alice's password change or revocation."""
    await _configure(scenario, MockSettingsPlanRequest(reject_phase=phase))
    async with create_browser() as intervening_browser:
        login = await submit_password_login(
            intervening_browser,
            email=scenario.human.email,
            password=SecretStr(scenario.human.password),
        )
        assert login.status_code == 200, "Could not establish the intervening session."
        response = await submit_password_settings(
            scenario.recovering_browser, scenario.settings, scenario.new_password
        )
        assert response.status_code == expected_status, "Expected a visible provider hook failure."
        saved = phase == "after"
        await _assert_password(scenario, SecretStr(scenario.human.password), accepted=not saved)
        await _assert_password(scenario, scenario.new_password, accepted=saved)
        assert (await intervening_browser.get("/sessions/whoami")).status_code == (
            401 if saved else 200
        )
        assert (await scenario.recovering_browser.get("/sessions/whoami")).status_code == 200
        snapshot = await _snapshot(scenario)
        assert [event.phase for event in snapshot.received] == (
            ["before", "after"] if saved else ["before"]
        )
        assert snapshot.acknowledged == (["before"] if saved else [])


@pytest.mark.asyncio
async def test_invalid_password_never_reaches_settings_hooks(
    scenario: PasswordResetScenarioDTO,
) -> None:
    """Password validation must reject bad input before cleanup callbacks run."""
    response = await submit_password_settings(
        scenario.recovering_browser, scenario.settings, SecretStr("short")
    )
    assert response.status_code == 400, "The weak replacement password was accepted."
    assert (await _snapshot(scenario)).received == []
    await _assert_password(scenario, SecretStr(scenario.human.password), accepted=True)


@pytest.mark.asyncio
async def test_settings_hooks_retain_recovery_request_flow_id(
    scenario: PasswordResetScenarioDTO,
) -> None:
    """The recovery-created settings flow retains the original request's flow ID.

    This qualifies a source of correlation evidence, not a production binding
    validator or durable callback handoff.
    """
    response = await submit_password_settings(
        scenario.recovering_browser, scenario.settings, scenario.new_password
    )
    assert response.status_code == 200, "Password setting did not finish."
    snapshot = await _snapshot(scenario)
    assert [event.phase for event in snapshot.received] == ["before", "after"]
    assert scenario.settings.id != scenario.recovery_flow_id
    assert all(
        event.source_recovery_flow_id == scenario.recovery_flow_id for event in snapshot.received
    )


@pytest.mark.asyncio
async def test_fresh_settings_flow_cannot_claim_recovery_through_query_parameter(
    scenario: PasswordResetScenarioDTO,
) -> None:
    """Sharing Alice's session and a caller-supplied flow ID does not bind a new flow."""
    started = await scenario.recovering_browser.get(
        "/self-service/settings/browser",
        params={"flow": str(scenario.recovery_flow_id)},
        headers={"Accept": "application/json"},
    )
    assert started.status_code == 200, "Could not start a separate settings flow."
    settings = SettingsFlowResponse.model_validate_json(started.text)
    assert settings.id != scenario.settings.id
    separate = replace(scenario, settings=settings)
    response = await submit_password_settings(
        separate.recovering_browser, settings, separate.new_password
    )
    assert response.status_code == 200, "The separate settings update did not finish."
    snapshot = await _snapshot(separate)
    assert [event.phase for event in snapshot.received] == ["before", "after"]
    assert all(event.source_recovery_flow_id is None for event in snapshot.received)
