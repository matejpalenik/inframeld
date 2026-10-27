import json
from unittest.mock import patch

import pytest
from ory_hydra_client import MetadataApi, OAuth2Api
from ory_hydra_client.models.health_status import HealthStatus

from inframeld_backend.access.application.errors.oauth_client_provisioning_rejected_error import (
    OAuthClientProvisioningRejectedError,
)
from inframeld_backend.access.application.errors.oauth_client_provisioning_uncertain_error import (
    OAuthClientProvisioningUncertainError,
)
from inframeld_backend.bootstrap.oauth_client_provisioning import main
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)


@pytest.fixture
def provider_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFRAMELD_HYDRA__ADMIN_URL", "http://hydra:4445")
    monkeypatch.setenv("INFRAMELD_HYDRA__ISSUER", "https://identity.test/")
    monkeypatch.setenv("INFRAMELD_HYDRA__API_AUDIENCE", "https://api.test")
    monkeypatch.delenv("INFRAMELD_DATABASE__PASSWORD", raising=False)
    monkeypatch.delenv("INFRAMELD_REQUEST_FINGERPRINT__KEY_FILE", raising=False)


@pytest.mark.parametrize("duration", ["invalid-secret-value", "５m", "5m١s"])
def test_invalid_lifetime_returns_safe_configuration_failure_before_sdk_io(
    provider_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    duration: str,
) -> None:
    monkeypatch.setenv("TTL_REFRESH_TOKEN", duration)
    with (
        patch.object(MetadataApi, "is_ready", return_value=HealthStatus(status="ok")) as ready,
        patch.object(OAuth2Api, "get_o_auth2_client") as read,
    ):
        assert main() == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["code"] == "invalid_configuration"
    assert "invalid-secret-value" not in captured.out + captured.err
    ready.assert_not_called()
    read.assert_not_called()


def test_matching_client_returns_json_without_application_database_settings(
    provider_environment: None, capsys: pytest.CaptureFixture[str]
) -> None:
    from ory_hydra_client.models.o_auth2_client import OAuth2Client

    profile = OAuth2Client(
        client_id="inframeld-cli",
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        redirect_uris=["http://127.0.0.1/oauth/callback"],
        scope="openid offline_access inframeld:api",
        audience=["https://api.test"],
        subject_type="public",
        access_token_strategy="opaque",
        skip_consent=False,
    )
    with (
        patch.object(MetadataApi, "is_ready", return_value=HealthStatus(status="ok")),
        patch.object(OAuth2Api, "get_o_auth2_client", return_value=profile),
        patch.object(OAuth2Api, "patch_o_auth2_client") as write,
    ):
        assert main() == 0
    assert json.loads(capsys.readouterr().out) == {
        "clientId": "inframeld-cli",
        "outcome": "unchanged",
    }
    write.assert_not_called()


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (OAuthClientProvisioningUncertainError("provider-secret"), "outcome_unknown"),
        (OAuthClientProvisioningRejectedError("provider-secret"), "configuration_rejected"),
        (DependencyUnavailableError("provider-secret"), "dependency_unavailable"),
    ],
)
def test_command_failure_reports_safe_distinct_outcomes(
    provider_environment: None, capsys: pytest.CaptureFixture[str], error: Exception, code: str
) -> None:
    with patch(
        "inframeld_backend.bootstrap.oauth_client_provisioning._provision", side_effect=error
    ):
        assert main() == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"clientId": "inframeld-cli", "code": code}
    assert "provider-secret" not in captured.out + captured.err


def test_validate_only_never_contacts_the_provider(
    provider_environment: None, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(MetadataApi, "is_ready") as ready:
        assert main(["--validate-only"]) == 0
    assert json.loads(capsys.readouterr().out) == {"outcome": "configuration_valid"}
    ready.assert_not_called()


def test_readiness_deadline_prevents_client_reads_or_writes(
    provider_environment: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("INFRAMELD_OAUTH_PROVISIONING__READINESS_TIMEOUT_SECONDS", "0.01")
    with (
        patch.object(MetadataApi, "is_ready", return_value=HealthStatus(status="error")) as ready,
        patch.object(OAuth2Api, "get_o_auth2_client") as read,
    ):
        assert main() == 1
    assert json.loads(capsys.readouterr().out)["code"] == "dependency_unavailable"
    assert 0 < ready.call_args.kwargs["_request_timeout"] <= 0.01
    read.assert_not_called()
