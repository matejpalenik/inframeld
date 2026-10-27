import asyncio
import math
from json import JSONDecodeError
from threading import Lock
from time import monotonic
from typing import Never, override

from ory_hydra_client import OAuth2Api
from ory_hydra_client.exceptions import ApiException, OpenApiException
from ory_hydra_client.models.json_patch import JsonPatch
from ory_hydra_client.models.o_auth2_client import OAuth2Client
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.enums.human_oauth_client_provisioning_outcome import (
    HumanOAuthClientProvisioningOutcome,
)
from inframeld_backend.access.application.errors.oauth_client_provisioning_rejected_error import (
    OAuthClientProvisioningRejectedError,
)
from inframeld_backend.access.application.errors.oauth_client_provisioning_uncertain_error import (
    OAuthClientProvisioningUncertainError,
)
from inframeld_backend.access.application.protocols.human_oauth_client_provisioner import (
    HumanOAuthClientProvisioner,
)
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)


class _ProvisioningCallState:
    """Give stopping and permission to dispatch a write one shared decision point."""

    def __init__(self, deadline: float) -> None:
        self._deadline = deadline
        self._lock = Lock()
        self._stopped = False
        self._write_admitted = False

    def remaining(self) -> float:
        with self._lock:
            return self._remaining()

    def admit_write(self) -> float:
        with self._lock:
            remaining = self._remaining()
            self._write_admitted = True
            return remaining

    def stop(self) -> bool:
        with self._lock:
            self._stopped = True
            return self._write_admitted

    def _remaining(self) -> float:
        remaining = self._deadline - monotonic()
        if self._stopped or remaining <= 0:
            raise TimeoutError
        return min(remaining, 5.0)


class HydraHumanOAuthClientProvisioner(HumanOAuthClientProvisioner):
    """Patch the managed registration through one SDK pool, without deleting login chains."""

    def __init__(self, client: OAuth2Api) -> None:
        self._client = client

    @override
    async def ensure_client(
        self, *, api_audience: HumanAPIAudience, timeout_seconds: float
    ) -> HumanOAuthClientProvisioningOutcome:
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("The provisioning deadline must be finite and positive.")
        state = _ProvisioningCallState(monotonic() + timeout_seconds)
        try:
            async with asyncio.timeout(timeout_seconds):
                return await asyncio.to_thread(
                    self._ensure,
                    api_audience,
                    state,
                )
        except ApiException:
            self._unavailable(state.stop())
        except (
            OpenApiException,
            HTTPError,
            ValidationError,
            JSONDecodeError,
            UnicodeDecodeError,
            TimeoutError,
            DependencyUnavailableError,
        ):
            self._unavailable(state.stop())
        finally:
            state.stop()

    @staticmethod
    def _unavailable(write_admitted: bool) -> Never:
        if write_admitted:
            raise OAuthClientProvisioningUncertainError(
                "The configuration may have applied. Rerun setup to inspect current state."
            ) from None
        raise DependencyUnavailableError() from None

    @staticmethod
    def _reject_permanent(error: ApiException) -> None:
        status: object = getattr(error, "status", None)
        if isinstance(status, int) and 400 <= status < 500 and status != 429:
            raise OAuthClientProvisioningRejectedError(
                "Hydra rejected the official client configuration."
            ) from None

    @staticmethod
    def _profile(audience: HumanAPIAudience) -> OAuth2Client:
        return OAuth2Client(
            client_id="inframeld-cli",
            client_name="Inframeld CLI",
            token_endpoint_auth_method="none",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            redirect_uris=["http://127.0.0.1/oauth/callback"],
            scope="openid offline_access inframeld:api",
            audience=[audience.value],
            subject_type="public",
            access_token_strategy="opaque",
            skip_consent=False,
        )

    @staticmethod
    def _changes(current: OAuth2Client, desired: OAuth2Client) -> list[JsonPatch]:
        # SDK JSON stays at this adapter boundary. Metadata and display names are not policy.
        observed: dict[str, object] = current.to_dict()
        expected: dict[str, object] = desired.to_dict()
        changes = [
            JsonPatch(op="add", path=f"/{name}", value=value)
            for name, value in expected.items()
            if name not in {"client_id", "client_name"} and observed.get(name) != value
        ]
        changes.extend(
            JsonPatch(op="remove", path=f"/{name}")
            for name, value in observed.items()
            if name.endswith("_lifespan") and value is not None
        )
        return changes

    def _ensure(
        self, audience: HumanAPIAudience, state: _ProvisioningCallState
    ) -> HumanOAuthClientProvisioningOutcome:
        def read() -> OAuth2Client | None:
            try:
                response = self._read_client(state.remaining())
            except ApiException as error:
                status: object = getattr(error, "status", None)
                if status == 404:
                    return None
                raise
            if not isinstance(response, OAuth2Client) or response.client_id != "inframeld-cli":
                raise DependencyUnavailableError()
            return response

        desired = self._profile(audience)
        current = read()
        if current is None:
            budget = state.admit_write()
            try:
                self._client.create_o_auth2_client(o_auth2_client=desired, _request_timeout=budget)
            except ApiException as error:
                status: object = getattr(error, "status", None)
                if status != 409:
                    self._reject_permanent(error)
                    raise
                winner = read()
                if winner is None or self._changes(winner, desired):
                    raise OAuthClientProvisioningRejectedError(
                        "Concurrent client setup returned a different profile."
                    ) from None
                return HumanOAuthClientProvisioningOutcome.UNCHANGED
            outcome = HumanOAuthClientProvisioningOutcome.CREATED
        else:
            changes = self._changes(current, desired)
            if not changes:
                return HumanOAuthClientProvisioningOutcome.UNCHANGED
            budget = state.admit_write()
            try:
                self._client.patch_o_auth2_client(
                    id="inframeld-cli", json_patch=changes, _request_timeout=budget
                )
            except ApiException as error:
                self._reject_permanent(error)
                raise
            outcome = HumanOAuthClientProvisioningOutcome.UPDATED
        confirmed = read()
        if confirmed is None or self._changes(confirmed, desired):
            raise OAuthClientProvisioningUncertainError(
                "The resulting client profile could not be confirmed."
            )
        state.remaining()
        return outcome

    def _read_client(self, timeout_seconds: float) -> object:
        return self._client.get_o_auth2_client(id="inframeld-cli", _request_timeout=timeout_seconds)
