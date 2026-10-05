import asyncio
from dataclasses import replace
from typing import Literal, override
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_verifier import (
    HumanAccessTokenVerifier,
)
from inframeld_backend.access.application.protocols.human_identity_link_reader import (
    HumanIdentityLinkReader,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.services.human_access_token_authentication_service import (
    HumanAccessTokenAuthenticationService,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)

type AuthenticationStep = Literal["token", "identity", "principal"]

IDENTITY = VerifiedHumanIdentityDTO(
    authority=IdentityAuthority("kratos:test"),
    subject=IdentitySubject("00000000-0000-4000-8000-000000000003"),
)
PRINCIPAL = Principal(
    id=PrincipalId(UUID("00000000-0000-4000-8000-000000000001")),
    organization_id=OrganizationId(UUID("00000000-0000-4000-8000-000000000002")),
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
CREDENTIAL = HumanAccessTokenCredential("synthetic-human-token")


async def _record_call(
    events: list[AuthenticationStep],
    step: AuthenticationStep,
    *,
    failure: Exception | None,
    blocked: bool,
) -> None:

    events.append(step)

    if failure is not None:
        raise failure

    if blocked:
        # Wait until service deadline cancels this dependency.
        await asyncio.Event().wait()


class MockTokenVerifier(HumanAccessTokenVerifier):
    def __init__(self, events: list[AuthenticationStep]) -> None:
        self.events = events
        self.result: VerifiedHumanIdentityDTO | None = IDENTITY
        self.failure: Exception | None = None
        self.blocked = False
        self.credentials: list[HumanAccessTokenCredential] = []
        self.budgets: list[float] = []

    @override
    async def verify(
        self, credential: HumanAccessTokenCredential, *, timeout_seconds: float
    ) -> VerifiedHumanIdentityDTO | None:
        self.credentials.append(credential)
        self.budgets.append(timeout_seconds)

        await _record_call(self.events, "token", failure=self.failure, blocked=self.blocked)

        return self.result


class MockIdentityVerifier(HumanIdentityVerifier):
    def __init__(self, events: list[AuthenticationStep]) -> None:
        self.events = events
        self.result: VerifiedHumanIdentityDTO | None = IDENTITY
        self.failure: Exception | None = None
        self.blocked = False
        self.identities: list[VerifiedHumanIdentityDTO] = []
        self.budgets: list[float] = []

    @override
    async def verify(
        self, identity: VerifiedHumanIdentityDTO, *, timeout_seconds: float
    ) -> VerifiedHumanIdentityDTO | None:
        self.identities.append(identity)
        self.budgets.append(timeout_seconds)

        await _record_call(self.events, "identity", failure=self.failure, blocked=self.blocked)

        return self.result


class MockPrincipalReader(HumanIdentityLinkReader):
    def __init__(self, events: list[AuthenticationStep]) -> None:
        self.events = events
        self.result: Principal | None = PRINCIPAL
        self.failure: Exception | None = None
        self.blocked = False
        self.return_after_cancellation = False
        self.identities: list[VerifiedHumanIdentityDTO] = []

    @override
    async def find_principal(
        self,
        identity: VerifiedHumanIdentityDTO,
    ) -> Principal | None:
        self.identities.append(identity)
        try:
            await _record_call(
                self.events,
                "principal",
                failure=self.failure,
                blocked=self.blocked,
            )
        except asyncio.CancelledError:
            if not self.return_after_cancellation:
                raise

            # Simulate a dependency returning a result after the deadline.
        return self.result


class AuthenticationScenario:
    def __init__(
        self,
        *,
        provider_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 10.0,
    ) -> None:
        self.events: list[AuthenticationStep] = []
        self.token = MockTokenVerifier(self.events)
        self.identity = MockIdentityVerifier(self.events)
        self.reader = MockPrincipalReader(self.events)
        self.service = HumanAccessTokenAuthenticationService(
            self.token,
            self.identity,
            self.reader,
            provider_timeout_seconds=provider_timeout_seconds,
            total_timeout_seconds=total_timeout_seconds,
        )


@pytest.mark.asyncio
async def test_valid_token_resolves_active_local_human() -> None:
    scenario = AuthenticationScenario()

    context = await scenario.service.authenticate(CREDENTIAL)

    assert context.actor_principal_id == PRINCIPAL.id
    assert scenario.events == ["token", "identity", "principal"]
    assert scenario.token.credentials == [CREDENTIAL]
    assert scenario.identity.identities == [IDENTITY]
    assert scenario.reader.identities == [IDENTITY]


@pytest.mark.asyncio
async def test_missing_credential_performs_no_io() -> None:
    scenario = AuthenticationScenario()

    with pytest.raises(AuthenticationRequiredError):
        await scenario.service.authenticate(None)

    assert scenario.events == []


@pytest.mark.asyncio
async def test_rejected_token_skips_identity_and_principal_checks() -> None:
    scenario = AuthenticationScenario()
    scenario.token.result = None

    with pytest.raises(AuthenticationRequiredError):
        await scenario.service.authenticate(CREDENTIAL)

    assert scenario.events == ["token"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "current_identity",
    [
        pytest.param(None, id="missing-or-ineligible"),
        pytest.param(
            replace(IDENTITY, authority=IdentityAuthority("kratos:other")),
            id="different-authority",
        ),
        pytest.param(
            replace(
                IDENTITY,
                subject=IdentitySubject("00000000-0000-4000-8000-000000000004"),
            ),
            id="different-subject",
        ),
    ],
)
async def test_current_identity_must_match_verified_token_identity(
    current_identity: VerifiedHumanIdentityDTO | None,
) -> None:
    scenario = AuthenticationScenario()
    scenario.identity.result = current_identity

    with pytest.raises(AuthenticationRequiredError):
        await scenario.service.authenticate(CREDENTIAL)

    assert scenario.events == ["token", "identity"]
    assert scenario.identity.identities == [IDENTITY]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "principal",
    [
        pytest.param(None, id="missing-local-link"),
        pytest.param(
            replace(PRINCIPAL, status=PrincipalStatus.SUSPENDED),
            id="suspended-human",
        ),
        pytest.param(
            replace(PRINCIPAL, status=PrincipalStatus.RETIRED),
            id="retired-human",
        ),
        pytest.param(
            replace(PRINCIPAL, kind=PrincipalKind.APPLICATION),
            id="application-principal",
        ),
    ],
)
async def test_local_admission_requires_an_active_human(
    principal: Principal | None,
) -> None:
    scenario = AuthenticationScenario()
    scenario.reader.result = principal

    with pytest.raises(AccessDeniedError):
        await scenario.service.authenticate(CREDENTIAL)

    assert scenario.events == ["token", "identity", "principal"]
    assert scenario.reader.identities == [IDENTITY]


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["token", "identity"])
@pytest.mark.parametrize(
    "failure_type",
    [DependencyUnavailableError, TimeoutError],
)
async def test_provider_failure_stops_authentication(
    step: Literal["token", "identity"],
    failure_type: type[DependencyUnavailableError | TimeoutError],
) -> None:
    scenario = AuthenticationScenario()
    failure = failure_type()

    if step == "token":
        scenario.token.failure = failure
        expected_events: list[AuthenticationStep] = ["token"]
    else:
        scenario.identity.failure = failure
        expected_events = ["token", "identity"]

    with pytest.raises(DependencyUnavailableError) as caught:
        await scenario.service.authenticate(CREDENTIAL)

    assert scenario.events == expected_events
    if isinstance(failure, TimeoutError):
        assert caught.value.__cause__ is failure
    else:
        assert caught.value is failure


@pytest.mark.asyncio
async def test_unexpected_local_read_failure_propagates() -> None:
    scenario = AuthenticationScenario()
    failure = RuntimeError("Synthetic persistence failure.")
    scenario.reader.failure = failure

    with pytest.raises(RuntimeError) as caught:
        await scenario.service.authenticate(CREDENTIAL)

    assert caught.value is failure
    assert scenario.events == ["token", "identity", "principal"]


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["token", "identity", "principal"])
async def test_total_deadline_bounds_every_dependency(
    step: AuthenticationStep,
) -> None:
    scenario = AuthenticationScenario(total_timeout_seconds=0.02)

    if step == "token":
        scenario.token.blocked = True
        expected_events: list[AuthenticationStep] = ["token"]
    elif step == "identity":
        scenario.identity.blocked = True
        expected_events = ["token", "identity"]
    else:
        scenario.reader.blocked = True
        expected_events = ["token", "identity", "principal"]

    # The outer guard makes a missing service deadline fail instead of hanging.
    async with asyncio.timeout(1.0):
        with pytest.raises(DependencyUnavailableError) as caught:
            await scenario.service.authenticate(CREDENTIAL)

    assert isinstance(caught.value.__cause__, TimeoutError)
    assert scenario.events == expected_events


@pytest.mark.asyncio
async def test_result_returned_after_deadline_cannot_authenticate() -> None:
    scenario = AuthenticationScenario(total_timeout_seconds=0.02)
    scenario.reader.blocked = True
    scenario.reader.return_after_cancellation = True

    async with asyncio.timeout(1.0):
        with pytest.raises(DependencyUnavailableError) as caught:
            await scenario.service.authenticate(CREDENTIAL)

    assert isinstance(caught.value.__cause__, TimeoutError)
    assert scenario.events == ["token", "identity", "principal"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_timeout_seconds", "total_timeout_seconds"),
    [(0.5, 10.0), (10.0, 0.5)],
)
async def test_provider_budgets_respect_provider_and_total_limits(
    provider_timeout_seconds: float,
    total_timeout_seconds: float,
) -> None:
    scenario = AuthenticationScenario(
        provider_timeout_seconds=provider_timeout_seconds,
        total_timeout_seconds=total_timeout_seconds,
    )

    await scenario.service.authenticate(CREDENTIAL)

    (token_budget,) = scenario.token.budgets
    (identity_budget,) = scenario.identity.budgets
    maximum_budget = min(provider_timeout_seconds, total_timeout_seconds)

    assert 0 < token_budget <= maximum_budget
    assert 0 < identity_budget <= token_budget


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_step", ["token", "identity", "principal"])
async def test_each_request_rechecks_current_admission(
    changed_step: AuthenticationStep,
) -> None:
    scenario = AuthenticationScenario()
    first_context = await scenario.service.authenticate(CREDENTIAL)
    assert first_context.actor_principal_id == PRINCIPAL.id
    scenario.events.clear()

    expected_error: type[AuthenticationRequiredError | AccessDeniedError]
    if changed_step == "token":
        scenario.token.result = None
        expected_error = AuthenticationRequiredError
        expected_events: list[AuthenticationStep] = ["token"]
    elif changed_step == "identity":
        scenario.identity.result = None
        expected_error = AuthenticationRequiredError
        expected_events = ["token", "identity"]
    else:
        scenario.reader.result = replace(
            PRINCIPAL,
            status=PrincipalStatus.SUSPENDED,
        )
        expected_error = AccessDeniedError
        expected_events = ["token", "identity", "principal"]

    with pytest.raises(expected_error):
        await scenario.service.authenticate(CREDENTIAL)

    assert scenario.events == expected_events
    assert scenario.token.credentials == [CREDENTIAL, CREDENTIAL]


@pytest.mark.parametrize("setting", ["provider", "total"])
@pytest.mark.parametrize(
    "seconds",
    [True, 0.0, -1.0, float("nan"), float("inf"), float("-inf")],
)
def test_timeouts_must_be_finite_positive_numbers(
    setting: Literal["provider", "total"],
    seconds: float,
) -> None:
    provider_timeout = seconds if setting == "provider" else 5.0
    total_timeout = seconds if setting == "total" else 10.0

    with pytest.raises(ValueError, match="finite and positive"):
        AuthenticationScenario(
            provider_timeout_seconds=provider_timeout,
            total_timeout_seconds=total_timeout,
        )
