import asyncio
import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager
from types import TracebackType
from typing import override
from unittest.mock import patch

import pytest
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from ory_hydra_client.exceptions import ApiException
from ory_hydra_client.models.o_auth2_client import OAuth2Client

from inframeld_backend.access.application.enums.human_oauth_client_provisioning_outcome import (
    HumanOAuthClientProvisioningOutcome,
)
from inframeld_backend.access.application.errors.oauth_client_provisioning_rejected_error import (
    OAuthClientProvisioningRejectedError,
)
from inframeld_backend.access.application.errors.oauth_client_provisioning_uncertain_error import (
    OAuthClientProvisioningUncertainError,
)
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.infrastructure.writers.hydra_human_oauth_client_provisioner import (
    HydraHumanOAuthClientProvisioner,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)

AUDIENCE = HumanAPIAudience("https://api.example.test")


class _MockWriteAdmissionLock(AbstractContextManager[None]):
    """Pause before or after the worker's write-admission critical section."""

    def __init__(self, entered: threading.Event, release: threading.Event, *, after: bool) -> None:
        self._lock = threading.Lock()
        self._entered = entered
        self._release = release
        self._after = after
        self._caller = threading.get_ident()
        self._worker_entries = 0

    @override
    def __enter__(self) -> None:
        if threading.get_ident() != self._caller:
            self._worker_entries += 1
            if self._worker_entries == 2 and not self._after:
                self._pause()
        self._lock.acquire()

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._lock.release()
        if threading.get_ident() != self._caller and self._worker_entries == 2 and self._after:
            self._pause()

    def _pause(self) -> None:
        self._entered.set()
        if not self._release.wait(5):
            raise TimeoutError


@pytest.fixture
def client() -> Iterator[OAuth2Api]:
    sdk = ApiClient(Configuration(host="http://hydra:4445", retries=0, debug=False))
    try:
        yield OAuth2Api(sdk)
    finally:
        sdk.rest_client.pool_manager.clear()


def _profile() -> OAuth2Client:
    return OAuth2Client(
        client_id="inframeld-cli",
        client_name="Operator's name",
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        redirect_uris=["http://127.0.0.1/oauth/callback"],
        scope="openid offline_access inframeld:api",
        audience=[AUDIENCE.value],
        subject_type="public",
        access_token_strategy="opaque",
        skip_consent=False,
        metadata={"operator": "preserved"},
    )


@pytest.mark.asyncio
async def test_missing_client_is_created_with_the_exact_profile_and_verified(
    client: OAuth2Api,
) -> None:
    """Installation configures one public client without deleting anything or returning secrets."""
    with (
        patch.object(
            client, "get_o_auth2_client", side_effect=[ApiException(status=404), _profile()]
        ) as read,
        patch.object(client, "create_o_auth2_client", return_value=_profile()) as create,
        patch.object(client, "delete_o_auth2_client") as delete,
    ):
        result = await HydraHumanOAuthClientProvisioner(client).ensure_client(
            api_audience=AUDIENCE, timeout_seconds=1
        )
    assert result is HumanOAuthClientProvisioningOutcome.CREATED
    assert read.call_count == 2
    create.assert_called_once()
    sent = create.call_args.kwargs["o_auth2_client"]
    assert isinstance(sent, OAuth2Client)
    assert sent.client_id == "inframeld-cli"
    assert sent.token_endpoint_auth_method == "none"
    assert sent.client_secret is None
    assert sent.grant_types == ["authorization_code", "refresh_token"]
    assert sent.response_types == ["code"]
    assert sent.scope == "openid offline_access inframeld:api"
    assert sent.audience == [AUDIENCE.value]
    assert sent.redirect_uris == ["http://127.0.0.1/oauth/callback"]
    assert sent.subject_type == "public" and sent.access_token_strategy == "opaque"
    assert sent.skip_consent is False
    assert 0 < create.call_args.kwargs["_request_timeout"] <= 1
    delete.assert_not_called()


@pytest.mark.asyncio
async def test_matching_registration_performs_no_write(client: OAuth2Api) -> None:
    with (
        patch.object(client, "get_o_auth2_client", return_value=_profile()),
        patch.object(client, "create_o_auth2_client") as create,
        patch.object(client, "patch_o_auth2_client") as update,
    ):
        assert (
            await HydraHumanOAuthClientProvisioner(client).ensure_client(
                api_audience=AUDIENCE, timeout_seconds=1
            )
            is HumanOAuthClientProvisioningOutcome.UNCHANGED
        )
    create.assert_not_called()
    update.assert_not_called()


@pytest.mark.asyncio
async def test_drift_is_patched_without_overwriting_metadata_or_retaining_hidden_lifetimes(
    client: OAuth2Api,
) -> None:
    current = _profile()
    current.skip_consent = True
    current.audience = ["https://wrong.test"]
    current.authorization_code_grant_access_token_lifespan = "3h"
    with (
        patch.object(client, "get_o_auth2_client", side_effect=[current, _profile()]),
        patch.object(client, "patch_o_auth2_client", return_value=_profile()) as update,
    ):
        assert (
            await HydraHumanOAuthClientProvisioner(client).ensure_client(
                api_audience=AUDIENCE, timeout_seconds=1
            )
            is HumanOAuthClientProvisioningOutcome.UPDATED
        )
    update.assert_called_once()
    patches = update.call_args.kwargs["json_patch"]
    assert {(p.op, p.path) for p in patches} == {
        ("add", "/skip_consent"),
        ("add", "/audience"),
        ("remove", "/authorization_code_grant_access_token_lifespan"),
    }
    assert next(p.value for p in patches if p.path == "/audience") == [AUDIENCE.value]


@pytest.mark.asyncio
@pytest.mark.parametrize("matches", [True, False])
async def test_concurrent_create_conflict_is_reread_once_without_another_mutation(
    client: OAuth2Api, matches: bool
) -> None:
    winner = _profile()
    if not matches:
        winner.skip_consent = True
    with (
        patch.object(
            client, "get_o_auth2_client", side_effect=[ApiException(status=404), winner]
        ) as read,
        patch.object(
            client, "create_o_auth2_client", side_effect=ApiException(status=409)
        ) as create,
        patch.object(client, "patch_o_auth2_client") as update,
    ):
        if matches:
            assert (
                await HydraHumanOAuthClientProvisioner(client).ensure_client(
                    api_audience=AUDIENCE, timeout_seconds=1
                )
                is HumanOAuthClientProvisioningOutcome.UNCHANGED
            )
        else:
            with pytest.raises(OAuthClientProvisioningRejectedError):
                await HydraHumanOAuthClientProvisioner(client).ensure_client(
                    api_audience=AUDIENCE, timeout_seconds=1
                )
    assert read.call_count == 2
    create.assert_called_once()
    update.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["read", "write", "verify"])
async def test_timeout_outcomes_distinguish_a_possible_write_from_an_unavailable_read(
    client: OAuth2Api, stage: str
) -> None:
    reads: list[object] = (
        [TimeoutError()]
        if stage == "read"
        else [ApiException(status=404), TimeoutError() if stage == "verify" else _profile()]
    )
    expected = (
        DependencyUnavailableError if stage == "read" else OAuthClientProvisioningUncertainError
    )
    with (
        patch.object(client, "get_o_auth2_client", side_effect=reads),
        patch.object(
            client,
            "create_o_auth2_client",
            side_effect=TimeoutError() if stage == "write" else None,
        ) as create,
        pytest.raises(expected) as failure,
    ):
        await HydraHumanOAuthClientProvisioner(client).ensure_client(
            api_audience=AUDIENCE, timeout_seconds=1
        )
    assert create.call_count == (0 if stage == "read" else 1)
    assert "secret" not in str(failure.value)


@pytest.mark.asyncio
async def test_explicit_rejection_is_safe_and_not_retried(client: OAuth2Api) -> None:
    with (
        patch.object(client, "get_o_auth2_client", side_effect=ApiException(status=404)),
        patch.object(
            client,
            "create_o_auth2_client",
            side_effect=ApiException(status=400, body="provider-secret"),
        ) as create,
        pytest.raises(OAuthClientProvisioningRejectedError) as failure,
    ):
        await HydraHumanOAuthClientProvisioner(client).ensure_client(
            api_audience=AUDIENCE, timeout_seconds=1
        )
    create.assert_called_once()
    assert "provider-secret" not in str(failure.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("observation", ["denied", "malformed"])
async def test_unverifiable_readback_after_creation_remains_uncertain(
    client: OAuth2Api, observation: str
) -> None:
    after = (
        ApiException(status=403)
        if observation == "denied"
        else OAuth2Client(client_id="wrong-client")
    )
    with (
        patch.object(client, "get_o_auth2_client", side_effect=[ApiException(status=404), after]),
        patch.object(client, "create_o_auth2_client", return_value=_profile()) as create,
        pytest.raises(OAuthClientProvisioningUncertainError),
    ):
        await HydraHumanOAuthClientProvisioner(client).ensure_client(
            api_audience=AUDIENCE, timeout_seconds=1
        )
    create.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("after_write", [False, True])
async def test_missing_sdk_envelope_never_confirms_configuration(
    client: OAuth2Api, after_write: bool
) -> None:
    responses = [ApiException(status=404), None] if after_write else [None]
    expected = OAuthClientProvisioningUncertainError if after_write else DependencyUnavailableError
    with (
        patch.object(client, "get_o_auth2_client", side_effect=responses),
        patch.object(client, "create_o_auth2_client", return_value=_profile()),
        pytest.raises(expected),
    ):
        await HydraHumanOAuthClientProvisioner(client).ensure_client(
            api_audience=AUDIENCE, timeout_seconds=1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_stopped_read_cannot_dispatch_a_later_write(client: OAuth2Api, cancel: bool) -> None:
    """A synchronous SDK thread may finish late, but must not start another setup step."""
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def blocked_read(*_args: object, **_kwargs: object) -> OAuth2Client:
        entered.set()
        try:
            if not release.wait(5):
                raise TimeoutError
            raise ApiException(status=404)
        finally:
            finished.set()

    with (
        patch.object(client, "get_o_auth2_client", side_effect=blocked_read),
        patch.object(client, "create_o_auth2_client") as create,
    ):
        task = asyncio.create_task(
            HydraHumanOAuthClientProvisioner(client).ensure_client(
                api_audience=AUDIENCE, timeout_seconds=1
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            if cancel:
                task.cancel()
            with pytest.raises(asyncio.CancelledError if cancel else DependencyUnavailableError):
                async with asyncio.timeout(5):
                    await task
            assert not finished.is_set()
        finally:
            release.set()
            assert await asyncio.to_thread(finished.wait, 5)
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        create.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("existing", [False, True])
async def test_stopping_before_write_admission_prevents_mutation(
    client: OAuth2Api, cancel: bool, existing: bool
) -> None:
    """Stopping between a read and write admission must prevent create and patch alike."""
    entered, release = threading.Event(), threading.Event()
    admission = _MockWriteAdmissionLock(entered, release, after=False)
    current = _profile()
    current.skip_consent = True
    with (
        patch(
            "inframeld_backend.access.infrastructure.writers.hydra_human_oauth_client_provisioner.Lock",
            return_value=admission,
        ),
        patch.object(
            client,
            "get_o_auth2_client",
            return_value=current,
            side_effect=None if existing else ApiException(status=404),
        ),
        patch.object(client, "create_o_auth2_client", return_value=_profile()) as create,
        patch.object(client, "patch_o_auth2_client", return_value=_profile()) as update,
    ):
        task = asyncio.create_task(
            HydraHumanOAuthClientProvisioner(client).ensure_client(
                api_audience=AUDIENCE, timeout_seconds=1
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            if cancel:
                task.cancel()
            with pytest.raises(asyncio.CancelledError if cancel else DependencyUnavailableError):
                async with asyncio.timeout(5):
                    await task
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            async with asyncio.timeout(5):
                await asyncio.get_running_loop().shutdown_default_executor()
        create.assert_not_called()
        update.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("existing", [False, True])
async def test_admitted_write_remains_uncertain_before_sdk_dispatch(
    client: OAuth2Api, cancel: bool, existing: bool
) -> None:
    """Once a write has permission to proceed, a stop cannot promise it will not run."""
    entered, release = threading.Event(), threading.Event()
    admission = _MockWriteAdmissionLock(entered, release, after=True)
    current = _profile()
    current.skip_consent = True
    with (
        patch(
            "inframeld_backend.access.infrastructure.writers.hydra_human_oauth_client_provisioner.Lock",
            return_value=admission,
        ),
        patch.object(
            client,
            "get_o_auth2_client",
            return_value=current,
            side_effect=None if existing else ApiException(status=404),
        ) as read,
        patch.object(client, "create_o_auth2_client", return_value=_profile()) as create,
        patch.object(client, "patch_o_auth2_client", return_value=_profile()) as update,
    ):
        task = asyncio.create_task(
            HydraHumanOAuthClientProvisioner(client).ensure_client(
                api_audience=AUDIENCE, timeout_seconds=1
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            if cancel:
                task.cancel()
            with pytest.raises(
                asyncio.CancelledError if cancel else OAuthClientProvisioningUncertainError
            ):
                async with asyncio.timeout(5):
                    await task
            create.assert_not_called()
            update.assert_not_called()
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            async with asyncio.timeout(5):
                await asyncio.get_running_loop().shutdown_default_executor()
        assert create.call_count == (0 if existing else 1)
        assert update.call_count == (1 if existing else 0)
        read.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [0.0, -1.0, float("nan"), float("inf"), True])
async def test_invalid_deadlines_cannot_reach_hydra(client: OAuth2Api, budget: float) -> None:
    with patch.object(client, "get_o_auth2_client") as read, pytest.raises(ValueError):
        await HydraHumanOAuthClientProvisioner(client).ensure_client(
            api_audience=AUDIENCE, timeout_seconds=budget
        )
    read.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_blocked_write_keeps_its_unknown_outcome_after_a_late_acknowledgement(
    client: OAuth2Api, cancel: bool
) -> None:
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def blocked_write(*_args: object, **_kwargs: object) -> OAuth2Client:
        entered.set()
        try:
            if not release.wait(5):
                raise TimeoutError
            return _profile()
        finally:
            finished.set()

    with (
        patch.object(client, "get_o_auth2_client", side_effect=ApiException(status=404)) as read,
        patch.object(client, "create_o_auth2_client", side_effect=blocked_write) as create,
    ):
        task = asyncio.create_task(
            HydraHumanOAuthClientProvisioner(client).ensure_client(
                api_audience=AUDIENCE, timeout_seconds=1
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            if cancel:
                task.cancel()
            with pytest.raises(
                asyncio.CancelledError if cancel else OAuthClientProvisioningUncertainError
            ):
                async with asyncio.timeout(5):
                    await task
            assert not finished.is_set()
        finally:
            release.set()
            assert await asyncio.to_thread(finished.wait, 5)
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        read.assert_called_once()
        create.assert_called_once()
        assert 0 < create.call_args.kwargs["_request_timeout"] <= 1
