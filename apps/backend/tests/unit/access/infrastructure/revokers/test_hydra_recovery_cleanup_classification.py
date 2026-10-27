from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import patch

import pytest
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from ory_hydra_client.api_response import ApiResponse
from ory_hydra_client.exceptions import ApiException

from inframeld_backend.access.application.dtos.human_oauth_cleanup_outcome_dto import (
    HumanOAuthCleanupOutcomeDTO,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.revokers.hydra_human_oauth_credential_revoker import (
    HydraHumanOAuthCredentialRevoker,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["cli_grants", "remembered_logins"])
@pytest.mark.parametrize(
    ("status", "state", "disposition"),
    [
        (204, State.CONFIRMED, "not_needed"),
        (429, State.FAILED, "retryable"),
        (408, State.UNCERTAIN, "retryable"),
        (500, State.UNCERTAIN, "retryable"),
        (503, State.UNCERTAIN, "retryable"),
        (501, State.UNCERTAIN, "operator_required"),
        (505, State.UNCERTAIN, "operator_required"),
        (404, State.FAILED, "operator_required"),
        (403, State.FAILED, "operator_required"),
        (302, State.UNCERTAIN, "operator_required"),
    ],
)
async def test_both_bulk_operations_classify_observations_without_retries(
    method: str, status: int, state: State, disposition: str
) -> None:
    sdk = ApiClient(Configuration(host="http://hydra.test:4445", retries=0, debug=False))
    api = OAuth2Api(sdk)
    operation = (
        "revoke_o_auth2_consent_sessions_with_http_info"
        if method == "cli_grants"
        else "revoke_o_auth2_login_sessions_with_http_info"
    )
    response = ApiResponse[None](status_code=204, headers=None, data=None, raw_data=b"")
    try:
        with patch.object(api, operation) as call:
            if status == 204:
                call.return_value = response
            else:
                call.side_effect = ApiException(status=status, body="must-not-escape")
            revoker = HydraHumanOAuthCredentialRevoker(api)
            result = await (
                revoker.revoke_cli_grants(IdentitySubject("alice"), timeout_seconds=1)
                if method == "cli_grants"
                else revoker.revoke_remembered_logins(IdentitySubject("alice"), timeout_seconds=1)
            )
            assert isinstance(result, HumanOAuthCleanupOutcomeDTO)
            assert (result.state, result.disposition, result.http_status) == (
                state,
                disposition,
                status,
            )
            assert "must-not-escape" not in repr(result)
            call.assert_called_once()
    finally:
        sdk.rest_client.pool_manager.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["120", "bad", "-2", "1.5", "past", "future"])
async def test_retry_after_is_retained_only_as_a_safe_parsed_delay(value: str) -> None:
    sdk = ApiClient(Configuration(host="http://hydra.test:4445", retries=0, debug=False))
    api = OAuth2Api(sdk)
    now = datetime.now(UTC)
    header = value
    if value in {"past", "future"}:
        header = format_datetime(now + timedelta(seconds=120 if value == "future" else -120))
    error = ApiException(status=429, body="private")
    error.headers = {"Retry-After": header}
    try:
        with patch.object(api, "revoke_o_auth2_consent_sessions_with_http_info", side_effect=error):
            result = await HydraHumanOAuthCredentialRevoker(api).revoke_cli_grants(
                IdentitySubject("alice"), timeout_seconds=1
            )
        assert isinstance(result, HumanOAuthCleanupOutcomeDTO)
        if value == "120":
            assert result.retry_after_seconds == 120
        elif value == "future":
            assert result.retry_after_seconds is not None
            assert 118 <= result.retry_after_seconds <= 120
        else:
            assert result.retry_after_seconds is None
    finally:
        sdk.rest_client.pool_manager.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [True, 99, 600, "503"])
async def test_invalid_status_is_protocol_uncertainty_without_publishing_invalid_metadata(
    status: object,
) -> None:
    sdk = ApiClient(Configuration(host="http://hydra.test:4445", retries=0, debug=False))
    api = OAuth2Api(sdk)
    error = ApiException(body="private")
    error.status = status
    try:
        with patch.object(api, "revoke_o_auth2_consent_sessions_with_http_info", side_effect=error):
            result = await HydraHumanOAuthCredentialRevoker(api).revoke_cli_grants(
                IdentitySubject("alice"), timeout_seconds=1
            )
        assert result.http_status is None
        assert result.disposition == "operator_required"
    finally:
        sdk.rest_client.pool_manager.clear()


@pytest.mark.asyncio
async def test_an_sdk_redirect_limit_is_protocol_uncertainty_requiring_attention() -> None:
    from urllib3 import HTTPConnectionPool
    from urllib3.exceptions import MaxRetryError, ResponseError

    sdk = ApiClient(Configuration(host="http://hydra.test:4445", retries=0, debug=False))
    api = OAuth2Api(sdk)
    pool = HTTPConnectionPool("hydra.test")
    error = MaxRetryError(pool, "/private", ResponseError("private"))
    try:
        with patch.object(
            api, "revoke_o_auth2_consent_sessions_with_http_info", side_effect=error
        ) as call:
            result = await HydraHumanOAuthCredentialRevoker(api).revoke_cli_grants(
                IdentitySubject("alice"), timeout_seconds=1
            )
        assert result.disposition == "operator_required"
        assert result.category == "provider_protocol_error"
        call.assert_called_once()
    finally:
        sdk.rest_client.pool_manager.clear()
        pool.close()
