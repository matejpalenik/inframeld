"""Run host-authorized OAuth configuration without starting the application."""

import asyncio
import json
from collections.abc import Sequence
from time import monotonic

from ory_hydra_client import ApiClient, Configuration, MetadataApi, OAuth2Api
from ory_hydra_client.exceptions import OpenApiException
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.errors.oauth_client_provisioning_rejected_error import (
    OAuthClientProvisioningRejectedError,
)
from inframeld_backend.access.application.errors.oauth_client_provisioning_uncertain_error import (
    OAuthClientProvisioningUncertainError,
)
from inframeld_backend.access.infrastructure.settings.oauth_client_provisioning_settings import (
    OAuthClientProvisioningSettings,
)
from inframeld_backend.access.infrastructure.writers.hydra_human_oauth_client_provisioner import (
    HydraHumanOAuthClientProvisioner,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)


async def _provision(settings: OAuthClientProvisioningSettings) -> str:
    sdk = ApiClient(
        Configuration(host=str(settings.hydra.admin_url).rstrip("/"), retries=0, debug=False)
    )
    try:
        metadata = MetadataApi(sdk)
        deadline = monotonic() + settings.readiness_timeout_seconds
        async with asyncio.timeout(settings.readiness_timeout_seconds):
            while True:
                try:
                    response = await asyncio.to_thread(
                        metadata.is_ready,
                        _request_timeout=min(2.0, max(0.001, deadline - monotonic())),
                    )
                except (OpenApiException, HTTPError, TimeoutError):
                    pass
                else:
                    if response.status == "ok":
                        break
                await asyncio.sleep(0.25)
        return await HydraHumanOAuthClientProvisioner(OAuth2Api(sdk)).ensure_client(
            api_audience=settings.hydra.api_audience, timeout_seconds=settings.timeout_seconds
        )
    finally:
        sdk.rest_client.pool_manager.clear()


def main(arguments: Sequence[str] = ()) -> int:
    """Print a safe outcome - uncertainty requires another explicit reconciliation."""
    if tuple(arguments) not in {(), ("--validate-only",)}:
        print(json.dumps({"code": "invalid_arguments"}))
        return 2
    try:
        settings = OAuthClientProvisioningSettings.model_validate({})
    except ValidationError:
        print(json.dumps({"code": "invalid_configuration"}))
        return 2
    if arguments:
        print(json.dumps({"outcome": "configuration_valid"}))
        return 0
    try:
        outcome = asyncio.run(_provision(settings))
    except OAuthClientProvisioningUncertainError:
        code = "outcome_unknown"
    except OAuthClientProvisioningRejectedError:
        code = "configuration_rejected"
    except (DependencyUnavailableError, OpenApiException, HTTPError, TimeoutError):
        code = "dependency_unavailable"
    except KeyboardInterrupt:
        code = "outcome_unknown"
    except Exception:
        code = "unexpected_error"
    else:
        print(json.dumps({"clientId": "inframeld-cli", "outcome": outcome}))
        return 0
    print(json.dumps({"clientId": "inframeld-cli", "code": code}))
    return 1
