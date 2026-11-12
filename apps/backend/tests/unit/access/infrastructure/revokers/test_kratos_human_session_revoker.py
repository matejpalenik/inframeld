import asyncio
from collections.abc import Iterator
from dataclasses import replace
from json import JSONDecodeError
from threading import Event
from unittest.mock import patch
from uuid import UUID

import pytest
from ory_kratos_client.api.identity_api import IdentityApi
from ory_kratos_client.api_client import ApiClient
from ory_kratos_client.api_response import ApiResponse
from ory_kratos_client.configuration import Configuration
from ory_kratos_client.exceptions import ApiException, OpenApiException
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.dtos.human_session_cleanup_outcome_dto import (
    HumanSessionCleanupOutcomeDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.revokers.kratos_human_session_revoker import (
    KratosHumanSessionRevoker,
)

AUTHORITY = IdentityAuthority("kratos:test")
IDENTITY = VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(str(UUID(int=42))))
METHOD = "delete_identity_sessions_with_http_info"


@pytest.fixture
def client() -> Iterator[IdentityApi]:
    sdk = ApiClient(Configuration(host="http://kratos-admin.test:4434", retries=0, debug=False))
    try:
        yield IdentityApi(sdk)
    finally:
        sdk.rest_client.pool_manager.clear()


@pytest.mark.asyncio
async def test_empty_on_time_204_revokes_only_the_exact_identity_once(client: IdentityApi) -> None:
    response = ApiResponse[None](status_code=204, headers=None, data=None, raw_data=b"")
    with patch.object(client, METHOD, return_value=response) as revoke:
        outcome = await KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
            IDENTITY, timeout_seconds=1
        )
    assert outcome.state is State.CONFIRMED and outcome.http_status == 204
    revoke.assert_called_once()
    arguments = dict(revoke.call_args.kwargs)
    timeout: object = arguments.pop("_request_timeout")
    assert isinstance(timeout, float) and 0 < timeout <= 1
    assert arguments == {"id": IDENTITY.subject.value}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity",
    [
        replace(IDENTITY, authority=IdentityAuthority("kratos:foreign")),
        replace(IDENTITY, subject=IdentitySubject("not-a-uuid")),
    ],
)
async def test_foreign_or_malformed_identity_prevents_provider_io(
    client: IdentityApi, identity: VerifiedHumanIdentityDTO
) -> None:
    with patch.object(client, METHOD) as revoke, pytest.raises(ValueError):
        await KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
            identity, timeout_seconds=1
        )
    revoke.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_seconds", [True, 0, -1, float("nan"), float("inf")])
async def test_invalid_original_budget_prevents_provider_io(
    client: IdentityApi, timeout_seconds: float
) -> None:
    with patch.object(client, METHOD) as revoke, pytest.raises(ValueError):
        await KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
            IDENTITY, timeout_seconds=timeout_seconds
        )
    revoke.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429])
async def test_explicit_rejection_is_failed_not_cleanup_or_nondispatch_proof(
    client: IdentityApi, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    with patch.object(
        client, METHOD, side_effect=ApiException(status=status, body="private-cookie")
    ) as revoke:
        outcome = await KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
            IDENTITY, timeout_seconds=1
        )
    assert outcome.state is State.FAILED and outcome.http_status == status
    assert "private-cookie" not in repr(outcome) + caplog.text
    revoke.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [408, 500, 501, 503, 505, 599])
async def test_every_server_error_and_408_remains_uncertain(
    client: IdentityApi, status: int
) -> None:
    with patch.object(
        client, METHOD, side_effect=ApiException(status=status, body="private")
    ) as revoke:
        outcome = await KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
            IDENTITY, timeout_seconds=1
        )
    assert outcome.state is State.UNCERTAIN and outcome.http_status == status
    revoke.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        HTTPError("private"),
        TimeoutError("private"),
        OpenApiException("private"),
        JSONDecodeError("private", "private", 0),
        UnicodeDecodeError("utf-8", b"private", 0, 1, "private"),
        ApiException(status=None, body="private"),
    ],
)
async def test_unconfirmed_transport_or_protocol_failures_never_retry_or_reflect_details(
    client: IdentityApi, failure: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    with patch.object(client, METHOD, side_effect=failure) as revoke:
        outcome = await KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
            IDENTITY, timeout_seconds=1
        )
    assert outcome.state is State.UNCERTAIN and outcome.http_status is None
    assert "private" not in repr(outcome) + caplog.text
    revoke.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        None,
        object(),
        ApiResponse[None](status_code=200, headers=None, data=None, raw_data=b""),
        ApiResponse[None](status_code=302, headers=None, data=None, raw_data=b""),
        ApiResponse[None](status_code=204, headers=None, data=None, raw_data=b"unexpected"),
    ],
)
async def test_only_the_expected_empty_204_confirms_cleanup(
    client: IdentityApi, response: object
) -> None:
    with patch.object(client, METHOD, return_value=response) as revoke:
        outcome = await KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
            IDENTITY, timeout_seconds=1
        )
    assert outcome.state is State.UNCERTAIN
    revoke.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [204, 404])
async def test_late_reply_is_uncertain_under_the_original_deadline(
    client: IdentityApi, status: int
) -> None:
    response = ApiResponse[None](status_code=status, headers=None, data=None, raw_data=b"")
    with (
        patch.object(client, METHOD, return_value=response) as revoke,
        patch(
            "inframeld_backend.access.infrastructure.revokers.kratos_human_session_revoker.monotonic",
            side_effect=[0.0, 0.01, 2.0],
            create=True,
        ),
    ):
        outcome = await KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
            IDENTITY, timeout_seconds=1
        )
    assert outcome.state is State.UNCERTAIN
    revoke.assert_called_once()


@pytest.mark.asyncio
async def test_exhausted_window_before_sdk_entry_does_not_start_another_window(
    client: IdentityApi,
) -> None:
    with (
        patch.object(client, METHOD) as revoke,
        patch(
            "inframeld_backend.access.infrastructure.revokers.kratos_human_session_revoker.monotonic",
            side_effect=[0.0, 2.0],
            create=True,
        ),
    ):
        outcome = await KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
            IDENTITY, timeout_seconds=1
        )
    assert outcome.state is State.UNCERTAIN
    revoke.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("behavior", ["deadline", "cancel"])
async def test_bounded_wait_and_cancellation_retire_the_mock_thread_before_return(
    client: IdentityApi, behavior: str
) -> None:
    started = asyncio.Event()
    release, finished = Event(), Event()
    loop = asyncio.get_running_loop()

    def blocked(**_kwargs: object) -> ApiResponse[None]:
        loop.call_soon_threadsafe(started.set)
        try:
            if not release.wait(timeout=2):
                raise TimeoutError()
            return ApiResponse[None](status_code=204, headers=None, data=None, raw_data=b"")
        finally:
            finished.set()

    work_error: BaseException | None = None
    task: asyncio.Task[HumanSessionCleanupOutcomeDTO] | None = None
    requested_cancel = False
    with patch.object(client, METHOD, side_effect=blocked) as revoke:
        try:
            task = asyncio.create_task(
                KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
                    IDENTITY, timeout_seconds=0.03 if behavior == "deadline" else 1
                )
            )
            async with asyncio.timeout(1):
                await started.wait()
            if behavior == "cancel":
                requested_cancel = True
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                outcome = await task
                assert outcome.state is State.UNCERTAIN
            assert not finished.is_set()
            revoke.assert_called_once()
        except BaseException as error:
            work_error = error
            raise
        finally:
            release.set()
            cleanup_errors: list[BaseException] = []
            try:
                async with asyncio.timeout(2):
                    if not await asyncio.to_thread(finished.wait, 1.0):
                        raise TimeoutError("The released SDK mock did not retire.")
            except BaseException as error:
                cleanup_errors.append(error)
            if task is not None:
                try:
                    async with asyncio.timeout(2):
                        if not task.done():
                            requested_cancel = True
                            task.cancel()
                        result = (
                            await asyncio.shield(asyncio.gather(task, return_exceptions=True))
                        )[0]
                    if (
                        isinstance(result, BaseException)
                        and result is not work_error
                        and not (requested_cancel and isinstance(result, asyncio.CancelledError))
                    ):
                        cleanup_errors.append(result)
                except BaseException as error:
                    if error is not work_error:
                        cleanup_errors.append(error)
            if cleanup_errors:
                raise BaseExceptionGroup(
                    "Provider test and independently bounded mock retirement failed",
                    ([work_error] if work_error is not None else []) + cleanup_errors,
                ) from None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [True, "401", 99, 600])
async def test_untrusted_sdk_status_is_not_reflected_as_a_valid_http_observation(
    client: IdentityApi, status: object
) -> None:
    with patch.object(client, METHOD, side_effect=ApiException(status=status)):
        outcome = await KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
            IDENTITY, timeout_seconds=1
        )
    assert outcome.state is State.UNCERTAIN and outcome.http_status is None


@pytest.mark.asyncio
async def test_late_sdk_rejection_is_not_a_timely_failed_observation(client: IdentityApi) -> None:
    with (
        patch.object(client, METHOD, side_effect=ApiException(status=404)) as revoke,
        patch(
            "inframeld_backend.access.infrastructure.revokers.kratos_human_session_revoker.monotonic",
            side_effect=[0.0, 0.01, 2.0],
        ),
    ):
        result = await KratosHumanSessionRevoker(client, AUTHORITY).revoke_sessions(
            IDENTITY, timeout_seconds=1
        )
    assert result.state is State.UNCERTAIN and result.http_status == 404
    revoke.assert_called_once()
