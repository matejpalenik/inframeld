import asyncio
from collections.abc import Iterator
from json import JSONDecodeError
from threading import Event
from typing import Literal
from unittest.mock import patch
from uuid import UUID

import pytest
from ory_kratos_client.api.identity_api import IdentityApi
from ory_kratos_client.api_client import ApiClient
from ory_kratos_client.configuration import Configuration
from ory_kratos_client.exceptions import ApiException, NotFoundException
from ory_kratos_client.models.identity import Identity
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.verifiers.kratos_human_identity_verifier import (
    KratosHumanIdentityVerifier,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)

AUTHORITY = IdentityAuthority("kratos:test")
IDENTITY_ID = UUID("00000000-0000-4000-8000-000000000003")
VERIFIED_IDENTITY = VerifiedHumanIdentityDTO(
    authority=AUTHORITY,
    subject=IdentitySubject(str(IDENTITY_ID)),
)


@pytest.fixture
def client() -> Iterator[IdentityApi]:
    sdk_client = ApiClient(
        Configuration(
            host="http://kratos-admin.test:4434",
            retries=0,
            debug=False,
        )
    )

    try:
        yield IdentityApi(sdk_client)
    finally:
        # This SDK release's context manager does not clear the HTTP pool.
        sdk_client.rest_client.pool_manager.clear()


def _identity(state: Literal["active", "inactive"] = "active") -> Identity:
    return Identity(
        id=str(IDENTITY_ID),
        schema_id="default",
        schema_url="http://kratos-admin.test:4434/schemas/default",
        traits=None,
        state=state,
    )


@pytest.mark.asyncio
async def test_active_identity_returns_the_same_verified_identity(client: IdentityApi) -> None:
    """Confirm an active account keeps the verified identity without requesting provider credentials."""
    verifier = KratosHumanIdentityVerifier(client, AUTHORITY)

    with patch.object(client, "get_identity", return_value=_identity()) as get_identity:
        result = await verifier.verify(VERIFIED_IDENTITY, timeout_seconds=2.0)

    assert result is VERIFIED_IDENTITY
    get_identity.assert_called_once()
    assert get_identity.call_args.kwargs["id"] == str(IDENTITY_ID)
    assert "include_credential" not in get_identity.call_args.kwargs

    request_timeout: object = get_identity.call_args.kwargs["_request_timeout"]
    assert isinstance(request_timeout, float)
    assert 0 < request_timeout <= 2.0


@pytest.mark.asyncio
async def test_inactive_identity_returns_no_identity(client: IdentityApi) -> None:
    """Prevent a disabled Kratos account from authenticating after its access token was accepted."""
    with patch.object(client, "get_identity", return_value=_identity("inactive")):
        result = await KratosHumanIdentityVerifier(client, AUTHORITY).verify(
            VERIFIED_IDENTITY,
            timeout_seconds=2.0,
        )

    assert result is None


@pytest.mark.asyncio
async def test_missing_identity_returns_no_identity(client: IdentityApi) -> None:
    """Treat a Kratos 404 response as a missing account that cannot authenticate."""
    with patch.object(
        client,
        "get_identity",
        side_effect=NotFoundException(status=404),
    ):
        result = await KratosHumanIdentityVerifier(client, AUTHORITY).verify(
            VERIFIED_IDENTITY,
            timeout_seconds=2.0,
        )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity",
    [
        VerifiedHumanIdentityDTO(
            authority=IdentityAuthority("kratos:another-installation"),
            subject=VERIFIED_IDENTITY.subject,
        ),
        VerifiedHumanIdentityDTO(
            authority=AUTHORITY,
            subject=IdentitySubject("alice@example.test"),
        ),
    ],
)
async def test_unsupported_identity_is_rejected_without_provider_io(
    client: IdentityApi,
    identity: VerifiedHumanIdentityDTO,
) -> None:
    """Require this installation's identity source and a valid account ID before calling Kratos."""
    with patch.object(client, "get_identity") as get_identity:
        result = await KratosHumanIdentityVerifier(client, AUTHORITY).verify(
            identity,
            timeout_seconds=2.0,
        )

    assert result is None
    get_identity.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        pytest.param(None, id="null-body"),
        pytest.param(_identity().model_copy(update={"state": None}), id="missing-state"),
        pytest.param(_identity().model_copy(update={"state": "unknown"}), id="unknown-state"),
        pytest.param(_identity().model_copy(update={"id": "invalid-id"}), id="invalid-id"),
        pytest.param(
            _identity().model_copy(update={"id": "00000000-0000-4000-8000-000000000004"}),
            id="different-identity",
        ),
    ],
)
async def test_malformed_or_unexpected_identity_is_unconfirmed(
    client: IdentityApi,
    response: object,
) -> None:
    """Fail safely when Kratos cannot confirm the exact account and its current status."""
    # model_copy deliberately bypasses SDK validation to exercise response checks.
    with (
        patch.object(client, "get_identity", return_value=response),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosHumanIdentityVerifier(client, AUTHORITY).verify(
            VERIFIED_IDENTITY,
            timeout_seconds=2.0,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        ApiException(status=401),
        ApiException(status=403),
        ApiException(status=500),
        HTTPError("Synthetic network failure."),
        TimeoutError(),
        JSONDecodeError("Malformed JSON.", "", 0),
    ],
)
async def test_provider_errors_are_unconfirmed(
    client: IdentityApi,
    failure: Exception,
) -> None:
    """Report an availability error when Kratos or network failures prevent an account check."""
    with (
        patch.object(client, "get_identity", side_effect=failure),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosHumanIdentityVerifier(client, AUTHORITY).verify(
            VERIFIED_IDENTITY,
            timeout_seconds=2.0,
        )


@pytest.mark.asyncio
async def test_sdk_schema_error_is_unconfirmed(client: IdentityApi) -> None:
    """Fail safely if the Kratos client cannot read the response's required fields."""
    with pytest.raises(ValidationError) as invalid:
        Identity.model_validate({})

    with (
        patch.object(client, "get_identity", side_effect=invalid.value),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosHumanIdentityVerifier(client, AUTHORITY).verify(
            VERIFIED_IDENTITY,
            timeout_seconds=2.0,
        )


@pytest.mark.asyncio
async def test_provider_error_details_are_hidden(client: IdentityApi) -> None:
    """Keep private provider data out of the error message and displayed exception traceback."""
    sensitive_detail = "synthetic-private-provider-data"

    with (
        patch.object(
            client,
            "get_identity",
            side_effect=ApiException(status=500, reason=sensitive_detail),
        ),
        pytest.raises(DependencyUnavailableError) as caught,
    ):
        await KratosHumanIdentityVerifier(client, AUTHORITY).verify(
            VERIFIED_IDENTITY,
            timeout_seconds=2.0,
        )

    assert sensitive_detail not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


@pytest.mark.asyncio
async def test_provider_deadline_stops_waiting_for_the_sdk(client: IdentityApi) -> None:
    """Stop waiting at the deadline even when the Kratos SDK call has not finished."""
    release = Event()

    def blocked_call(**_kwargs: object) -> Identity:
        release.wait(timeout=1.0)
        return _identity()

    try:
        with patch.object(client, "get_identity", side_effect=blocked_call):
            async with asyncio.timeout(2.0):
                with pytest.raises(DependencyUnavailableError):
                    await KratosHumanIdentityVerifier(client, AUTHORITY).verify(
                        VERIFIED_IDENTITY,
                        timeout_seconds=0.02,
                    )
    finally:
        release.set()


@pytest.mark.asyncio
async def test_next_request_rechecks_kratos_after_identity_is_disabled(client: IdentityApi) -> None:
    """Recheck Kratos on the next request so a newly disabled account is rejected."""
    verifier = KratosHumanIdentityVerifier(client, AUTHORITY)

    with patch.object(
        client,
        "get_identity",
        side_effect=[_identity(), _identity("inactive")],
    ) as get_identity:
        first = await verifier.verify(VERIFIED_IDENTITY, timeout_seconds=2.0)
        second = await verifier.verify(VERIFIED_IDENTITY, timeout_seconds=2.0)

    assert first is VERIFIED_IDENTITY
    assert second is None
    assert get_identity.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_seconds", [0.0, -1.0, float("inf"), float("nan"), True])
async def test_invalid_provider_budget_is_rejected_before_io(
    client: IdentityApi,
    timeout_seconds: float,
) -> None:
    """Reject invalid time limits before contacting Kratos so verification has a usable deadline."""
    with (
        patch.object(client, "get_identity") as get_identity,
        pytest.raises(ValueError, match="finite and positive"),
    ):
        await KratosHumanIdentityVerifier(client, AUTHORITY).verify(
            VERIFIED_IDENTITY,
            timeout_seconds=timeout_seconds,
        )

    get_identity.assert_not_called()
