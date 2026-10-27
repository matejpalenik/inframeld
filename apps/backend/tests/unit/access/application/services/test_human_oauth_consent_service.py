"""Keep CLI approval tied to the current browser and recovery state."""

import asyncio
from dataclasses import dataclass, field, replace
from typing import Literal, override

import pytest
from tests.support.mock_human_credential_state_reader import MockHumanCredentialStateReader

from inframeld_backend.access.application.commands.decide_human_oauth_consent_command import (
    DecideHumanOAuthConsentCommand,
)
from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_consent_details_dto import (
    HumanOAuthConsentDetailsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_consent_request_dto import (
    HumanOAuthConsentRequestDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.oauth_consent_continuation_dto import (
    OAuthConsentContinuationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.oauth_consent_decision import OAuthConsentDecision
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.protocols.identity_recovery_block_reader import (
    IdentityRecoveryBlockReader,
)
from inframeld_backend.access.application.protocols.oauth_consent_decision_writer import (
    OAuthConsentDecisionWriter,
)
from inframeld_backend.access.application.protocols.oauth_consent_request_reader import (
    OAuthConsentRequestReader,
)
from inframeld_backend.access.application.queries.inspect_human_oauth_consent_query import (
    InspectHumanOAuthConsentQuery,
)
from inframeld_backend.access.application.services.human_oauth_consent_service import (
    HumanOAuthConsentService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.oauth_client_id import OAuthClientId
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)

AUTHORITY = IdentityAuthority("kratos:test")
IDENTITY = VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject("alice"))
AUDIENCE = HumanAPIAudience("https://api.example.test")
CHALLENGE = OAuthConsentChallenge("private-consent-challenge")
COOKIE = BrowserSessionCredential("private-cookie")
REQUEST = HumanOAuthConsentRequestDTO(
    IDENTITY.subject,
    OAuthClientId("inframeld-cli"),
    (HumanOAuthScope.API, HumanOAuthScope.OFFLINE_ACCESS),
    (AUDIENCE,),
    False,
)
CONTINUATION = OAuthConsentContinuationDTO(
    "https://auth.example.test/oauth2/auth?consent_verifier=secret"
)


@dataclass
class MockConsentRequestReader(OAuthConsentRequestReader):
    calls: list[str]
    request: HumanOAuthConsentRequestDTO = REQUEST
    error: Exception | None = None
    wait: bool = False

    @override
    async def read(
        self, challenge: OAuthConsentChallenge, *, timeout_seconds: float
    ) -> HumanOAuthConsentRequestDTO:
        assert challenge is CHALLENGE
        assert 0 < timeout_seconds <= 5
        self.calls.append("read")
        if self.wait:
            await asyncio.Event().wait()
        if self.error:
            raise self.error
        return self.request


@dataclass
class MockBrowserVerifier(BrowserSessionVerifier):
    calls: list[str]
    identity: VerifiedHumanIdentityDTO | None = IDENTITY
    wait: bool = False

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        assert credential is COOKIE
        self.calls.append("verify")
        if self.wait:
            await asyncio.Event().wait()
        return self.identity


@dataclass
class MockRecoveryBlocks(IdentityRecoveryBlockReader):
    calls: list[str]
    blocked: bool = False
    error: Exception | None = None
    wait: bool = False

    @override
    async def is_blocked(self, identity: VerifiedHumanIdentityDTO) -> bool:
        assert identity is IDENTITY
        self.calls.append("block")
        if self.wait:
            await asyncio.Event().wait()
        if self.error:
            raise self.error
        return self.blocked


@dataclass
class MockConsentDecisionWriter(OAuthConsentDecisionWriter):
    calls: list[str]
    remembered: list[int | None] = field(default_factory=list[int | None])
    error: Exception | None = None
    wait: bool = False
    bindings: list[HumanOAuthCredentialBindingDTO] = field(
        default_factory=list[HumanOAuthCredentialBindingDTO]
    )

    @override
    async def allow(
        self,
        challenge: OAuthConsentChallenge,
        *,
        scopes: tuple[HumanOAuthScope, ...],
        audiences: tuple[HumanAPIAudience, ...],
        remember_for_seconds: int | None,
        binding: HumanOAuthCredentialBindingDTO,
        timeout_seconds: float,
    ) -> OAuthConsentContinuationDTO:
        assert challenge is CHALLENGE
        assert scopes == REQUEST.scopes
        assert audiences == (AUDIENCE,)
        assert 0 < timeout_seconds <= 5
        self.calls.append("allow")
        self.remembered.append(remember_for_seconds)
        self.bindings.append(binding)
        if self.wait:
            await asyncio.Event().wait()
        if self.error:
            raise self.error
        return CONTINUATION

    @override
    async def deny(
        self, challenge: OAuthConsentChallenge, *, timeout_seconds: float
    ) -> OAuthConsentContinuationDTO:
        assert challenge is CHALLENGE
        self.calls.append("deny")
        return CONTINUATION


class MockConsentScenario:
    def __init__(
        self, *, total_timeout_seconds: float = 10.0, remember_consent_seconds: int = 3600
    ) -> None:
        self.calls: list[str] = []
        self.reader = MockConsentRequestReader(self.calls)
        self.verifier = MockBrowserVerifier(self.calls)
        self.blocks = MockRecoveryBlocks(self.calls)
        self.writer = MockConsentDecisionWriter(self.calls)
        self.states = MockHumanCredentialStateReader(events=self.calls)
        self.service = HumanOAuthConsentService(
            self.reader,
            self.writer,
            self.verifier,
            self.blocks,
            credential_states=self.states,
            credential_initializer=self.states,
            authority=AUTHORITY,
            api_audience=AUDIENCE,
            remember_consent_seconds=remember_consent_seconds,
            total_timeout_seconds=total_timeout_seconds,
        )

    async def allow(self, *, remember: bool = False) -> OAuthConsentContinuationDTO:
        return await self.service.decide(
            credential=COOKIE,
            command=DecideHumanOAuthConsentCommand(CHALLENGE, OAuthConsentDecision.ALLOW, remember),
        )

    async def inspect(self) -> HumanOAuthConsentDetailsDTO:
        return await self.service.inspect(
            credential=COOKIE, query=InspectHumanOAuthConsentQuery(CHALLENGE)
        )

    async def deny(self) -> OAuthConsentContinuationDTO:
        return await self.service.decide(
            credential=COOKIE,
            command=DecideHumanOAuthConsentCommand(CHALLENGE, OAuthConsentDecision.DENY, True),
        )


@pytest.mark.asyncio
async def test_inspection_checks_current_identity_and_block_without_approving() -> None:
    """An unadmitted Alice can inspect OAuth access without gaining product permissions."""
    scenario = MockConsentScenario()
    details = await scenario.inspect()
    assert details.identity is IDENTITY
    assert details.installation == AUDIENCE
    assert details.client_id == REQUEST.client_id
    assert details.scopes == REQUEST.scopes
    assert details.audiences == (AUDIENCE,)
    assert details.approval_required
    assert details.remember_consent_seconds == 3600
    assert scenario.calls == ["read", "verify", "block"]


@pytest.mark.asyncio
@pytest.mark.parametrize("remember,seconds", [(False, None), (True, 3600)])
async def test_allow_uses_checked_access_and_server_remember_duration(
    remember: bool, seconds: int | None
) -> None:
    scenario = MockConsentScenario()
    assert await scenario.allow(remember=remember) is CONTINUATION
    assert scenario.calls == ["read", "initialize", "verify", "block", "allow"]
    assert scenario.writer.remembered == [seconds]


@pytest.mark.asyncio
async def test_custom_remember_duration_is_forwarded() -> None:
    scenario = MockConsentScenario(remember_consent_seconds=7200)
    await scenario.allow(remember=True)
    assert scenario.writer.remembered == [7200]


@pytest.mark.asyncio
async def test_remembered_consent_is_rechecked_without_extending_its_lifetime() -> None:
    scenario = MockConsentScenario()
    scenario.reader.request = replace(REQUEST, skip=True)
    assert not (await scenario.inspect()).approval_required
    await scenario.allow(remember=True)
    assert scenario.calls == [
        "read",
        "verify",
        "block",
        "read",
        "initialize",
        "verify",
        "block",
        "allow",
    ]
    assert scenario.writer.remembered == [None]


@pytest.mark.asyncio
async def test_deny_returns_only_the_provider_continuation() -> None:
    scenario = MockConsentScenario()
    result = await scenario.deny()
    assert result is CONTINUATION
    assert scenario.calls == ["read", "verify", "block", "deny"]
    assert not scenario.writer.remembered
    assert not scenario.states.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["inspect", "allow", "deny"])
@pytest.mark.parametrize(
    "failure",
    [
        "invalid_session",
        "different_subject",
        "different_authority",
        "recovery",
        "client",
        "scope",
        "audience",
    ],
)
async def test_rejected_requests_cannot_approve_or_reject_someone_elses_consent(
    operation: Literal["inspect", "allow", "deny"], failure: str
) -> None:
    scenario = MockConsentScenario()
    error_type = AccessDeniedError
    if failure == "invalid_session":
        scenario.verifier.identity = None
        error_type = AuthenticationRequiredError
    elif failure == "different_subject":
        scenario.reader.request = replace(REQUEST, subject=IdentitySubject("bob"))
    elif failure == "different_authority":
        scenario.verifier.identity = VerifiedHumanIdentityDTO(
            IdentityAuthority("other"), IDENTITY.subject
        )
    elif failure == "recovery":
        scenario.blocks.blocked = True
        scenario.states.result = True
    elif failure == "client":
        scenario.reader.request = replace(REQUEST, client_id=OAuthClientId("other-client"))
    elif failure == "scope":
        scenario.reader.request = replace(REQUEST, scopes=(HumanOAuthScope.OPENID,))
    else:
        scenario.reader.request = replace(
            REQUEST, audiences=(HumanAPIAudience("https://other.test"),)
        )
    with pytest.raises(error_type):
        if operation == "inspect":
            await scenario.inspect()
        elif operation == "deny":
            await scenario.deny()
        else:
            await scenario.allow()
    assert "allow" not in scenario.calls
    assert "deny" not in scenario.calls
    if failure == "invalid_session":
        assert scenario.calls == (
            ["read", "initialize", "verify"] if operation == "allow" else ["read", "verify"]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["inspect", "allow", "deny"])
@pytest.mark.parametrize("unsupported", ["client", "scope", "audience"])
@pytest.mark.parametrize("invalid_cookie", [False, True])
async def test_unsupported_access_stops_before_browser_checks_or_state_initialization(
    operation: Literal["inspect", "allow", "deny"], unsupported: str, invalid_cookie: bool
) -> None:
    """An unrelated OAuth request cannot initialize Alice's credential state."""
    scenario = MockConsentScenario()
    if unsupported == "client":
        scenario.reader.request = replace(REQUEST, client_id=OAuthClientId("other-client"))
    elif unsupported == "scope":
        scenario.reader.request = replace(REQUEST, scopes=(HumanOAuthScope.OPENID,))
    else:
        scenario.reader.request = replace(
            REQUEST, audiences=(HumanAPIAudience("https://other.test"),)
        )
    if invalid_cookie:
        scenario.verifier.identity = None

    with pytest.raises(AccessDeniedError):
        if operation == "inspect":
            await scenario.inspect()
        elif operation == "deny":
            await scenario.deny()
        else:
            await scenario.allow()

    assert scenario.calls == ["read"]
    assert not scenario.states.calls


@pytest.mark.asyncio
async def test_inspection_does_not_authorize_a_later_decision_after_recovery_starts() -> None:
    scenario = MockConsentScenario()
    await scenario.inspect()
    scenario.blocks.blocked = True
    scenario.states.result = True
    with pytest.raises(AccessDeniedError):
        await scenario.allow()
    assert scenario.calls == ["read", "verify", "block", "read", "initialize", "verify", "block"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["read", "block", "allow"])
async def test_availability_failures_propagate_without_an_automatic_retry(stage: str) -> None:
    scenario = MockConsentScenario()
    error = DependencyUnavailableError()
    if stage == "read":
        scenario.reader.error = error
    elif stage == "block":
        scenario.states.failure = error
    else:
        scenario.writer.error = error
    with pytest.raises(DependencyUnavailableError) as caught:
        await scenario.allow()
    assert caught.value is error
    assert scenario.calls.count(stage) == 1


@pytest.mark.asyncio
async def test_unusable_challenge_keeps_its_safe_not_found_outcome() -> None:
    scenario = MockConsentScenario()
    scenario.reader.error = ResourceNotFoundError()
    with pytest.raises(ResourceNotFoundError):
        await scenario.allow()
    assert scenario.calls == ["read"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["read", "initialize", "verify", "block", "allow"])
async def test_total_deadline_bounds_each_stage_without_retry(stage: str) -> None:
    scenario = MockConsentScenario(total_timeout_seconds=0.01)
    if stage == "read":
        scenario.reader.wait = True
    elif stage == "initialize":
        scenario.states.initialization_stall = True
    elif stage == "verify":
        scenario.verifier.wait = True
    elif stage == "block":
        scenario.states.stall = True
    else:
        scenario.writer.wait = True
    with pytest.raises(DependencyUnavailableError):
        await scenario.allow()
    assert scenario.calls.count(stage) == 1
    stages = ["read", "initialize", "verify", "block", "allow"]
    assert scenario.calls == stages[: stages.index(stage) + 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["inspect", "deny"])
@pytest.mark.parametrize("failure", ["unavailable", "deadline"])
async def test_read_only_checks_fail_without_initializing_or_submitting_a_decision(
    operation: Literal["inspect", "deny"], failure: str
) -> None:
    scenario = MockConsentScenario(total_timeout_seconds=0.01)
    if failure == "unavailable":
        scenario.blocks.error = DependencyUnavailableError()
    else:
        scenario.blocks.wait = True
    with pytest.raises(DependencyUnavailableError):
        if operation == "inspect":
            await scenario.inspect()
        else:
            await scenario.deny()
    assert scenario.calls == ["read", "verify", "block"]
    assert not scenario.states.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["read", "initialize", "verify", "block", "allow"])
async def test_cancellation_propagates_without_retrying_the_interrupted_stage(stage: str) -> None:
    scenario = MockConsentScenario()
    if stage == "read":
        scenario.reader.wait = True
    elif stage == "initialize":
        scenario.states.initialization_stall = True
    elif stage == "verify":
        scenario.verifier.wait = True
    elif stage == "block":
        scenario.states.stall = True
    else:
        scenario.writer.wait = True
    task = asyncio.create_task(scenario.allow())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    stages = ["read", "initialize", "verify", "block", "allow"]
    assert scenario.calls == stages[: stages.index(stage) + 1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        "version",
        "initial_block",
        "final_block",
        "installation",
        "initial_identity",
        "final_identity",
        "missing_version",
    ],
)
async def test_allow_rejects_security_state_crossing_browser_verification(changed: str) -> None:
    """An old proof cannot inherit a new version or survive a block that clears mid-check."""
    scenario = MockConsentScenario()
    first = HumanCredentialStateDTO(
        scenario.states.installation_id,
        IDENTITY,
        HumanCredentialVersion(1),
        changed == "initial_block",
    )
    final = replace(
        first,
        version=HumanCredentialVersion(2) if changed == "version" else first.version,
        has_pending_recovery=changed == "final_block",
    )
    if changed == "installation":
        from uuid import UUID

        from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

        final = replace(final, installation_id=InstallationId(UUID(int=999)))
    elif changed == "initial_identity":
        first = replace(first, identity=replace(IDENTITY, subject=IdentitySubject("bob")))
    elif changed == "final_identity":
        final = replace(final, identity=replace(IDENTITY, subject=IdentitySubject("bob")))
    elif changed == "missing_version":
        first = replace(first, version=None)
        final = replace(final, version=None)
    scenario.states.snapshots = [first, final]
    with pytest.raises(AccessDeniedError):
        await scenario.allow()
    assert not scenario.writer.bindings


@pytest.mark.asyncio
async def test_allow_passes_the_captured_binding_and_inspection_never_initializes() -> None:
    scenario = MockConsentScenario()
    await scenario.inspect()
    assert not scenario.states.calls
    await scenario.allow()
    assert scenario.states.calls == ["initialize", "state"]
    assert scenario.writer.bindings == [
        HumanOAuthCredentialBindingDTO(
            IDENTITY, scenario.states.installation_id, HumanCredentialVersion(1)
        )
    ]


@pytest.mark.asyncio
async def test_initialization_failure_cannot_reach_browser_verification_or_approval() -> None:
    scenario = MockConsentScenario()
    scenario.states.initialization_failure = DependencyUnavailableError()
    with pytest.raises(DependencyUnavailableError):
        await scenario.allow()
    assert scenario.calls == ["read", "initialize"]


@pytest.mark.asyncio
async def test_initialization_is_included_in_the_total_deadline() -> None:
    scenario = MockConsentScenario(total_timeout_seconds=0.01)
    scenario.states.initialization_stall = True
    with pytest.raises(DependencyUnavailableError):
        await scenario.allow()
    assert scenario.calls == ["read", "initialize"]
