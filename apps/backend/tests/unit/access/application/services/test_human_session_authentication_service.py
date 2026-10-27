"""Verify provider authentication and local admission as one application workflow."""

import asyncio
from contextlib import suppress
from dataclasses import replace
from typing import Literal, override
from uuid import uuid4

import pytest
from tests.support.mock_identity_recovery_block_reader import MockIdentityRecoveryBlockReader

from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.protocols.human_identity_link_reader import (
    HumanIdentityLinkReader,
)
from inframeld_backend.access.application.services.human_session_authentication_service import (
    HumanSessionAuthenticationService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
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

IDENTITY = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice"))
PRINCIPAL = Principal(
    PrincipalId(uuid4()), OrganizationId(uuid4()), PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
CREDENTIAL = BrowserSessionCredential("synthetic-secret")


class FixedVerifier(BrowserSessionVerifier):
    """Return a provider outcome and record whether verification was attempted."""

    def __init__(
        self, identity: VerifiedHumanIdentityDTO | None = IDENTITY, failure: Exception | None = None
    ) -> None:
        """Choose the provider result used by an authentication scenario."""
        self.identity = identity
        self.failure = failure
        self.called = False

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        """Represent provider verification without performing network I/O."""
        self.called = True
        if self.failure is not None:
            raise self.failure
        return self.identity


class FixedPrincipalReader(HumanIdentityLinkReader):
    """Supply linked principal state and record the exact verified identity used."""

    def __init__(self, principal: Principal | None = PRINCIPAL) -> None:
        """Choose the local principal returned by the read boundary."""
        self.principal = principal
        self.identity: VerifiedHumanIdentityDTO | None = None

    @override
    async def find_principal(self, identity: VerifiedHumanIdentityDTO) -> Principal | None:
        """Return current local state for the identity supplied by verification."""
        self.identity = identity
        return self.principal


class MockDeadlineBrowserVerifier(BrowserSessionVerifier):
    """Simulate a provider that stalls or returns a result after cancellation."""

    def __init__(self) -> None:
        self.blocked = False
        self.return_after_cancellation = False
        self.result: VerifiedHumanIdentityDTO | None = IDENTITY
        self.started = asyncio.Event()

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        self.started.set()
        if self.blocked:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if not self.return_after_cancellation:
                    raise
        return self.result


class MockDeadlinePrincipalReader(HumanIdentityLinkReader):
    """Simulate a local read that can outlast the authentication deadline."""

    def __init__(self) -> None:
        self.called = False
        self.blocked = False
        self.return_after_cancellation = False
        self.result: Principal | None = PRINCIPAL

    @override
    async def find_principal(self, identity: VerifiedHumanIdentityDTO) -> Principal | None:
        self.called = True
        if self.blocked:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if not self.return_after_cancellation:
                    raise
        return self.result


@pytest.mark.asyncio
async def test_valid_identity_resolves_active_local_human() -> None:
    """Carry browser authentication evidence alongside the admitted local actor."""
    reader = FixedPrincipalReader()
    context = await HumanSessionAuthenticationService(
        FixedVerifier(), reader, recovery_block_reader=MockIdentityRecoveryBlockReader()
    ).authenticate(CREDENTIAL)
    assert context.actor_principal_id == PRINCIPAL.id
    assert context.authentication_evidence == BrowserSessionAuthenticationDTO(IDENTITY)
    assert reader.identity == IDENTITY


@pytest.mark.asyncio
async def test_missing_credential_performs_no_io() -> None:
    """Reject a missing session before contacting either external dependency."""
    verifier, reader = FixedVerifier(), FixedPrincipalReader()
    with pytest.raises(AuthenticationRequiredError):
        await HumanSessionAuthenticationService(
            verifier, reader, recovery_block_reader=MockIdentityRecoveryBlockReader()
        ).authenticate(None)
    assert not verifier.called
    assert reader.identity is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "principal",
    [
        None,
        replace(PRINCIPAL, status=PrincipalStatus.SUSPENDED),
        replace(PRINCIPAL, status=PrincipalStatus.RETIRED),
        replace(PRINCIPAL, kind=PrincipalKind.APPLICATION),
    ],
)
async def test_verified_identity_requires_an_active_local_human(
    principal: Principal | None,
) -> None:
    """Deny absent links, inactive humans, and application principals."""
    with pytest.raises(AccessDeniedError):
        await HumanSessionAuthenticationService(
            FixedVerifier(),
            FixedPrincipalReader(principal),
            recovery_block_reader=MockIdentityRecoveryBlockReader(),
        ).authenticate(CREDENTIAL)


@pytest.mark.asyncio
async def test_rejected_session_skips_local_lookup() -> None:
    """Require successful provider verification before reading local principal state."""
    reader = FixedPrincipalReader()
    with pytest.raises(AuthenticationRequiredError):
        await HumanSessionAuthenticationService(
            FixedVerifier(None), reader, recovery_block_reader=MockIdentityRecoveryBlockReader()
        ).authenticate(CREDENTIAL)
    assert reader.identity is None


@pytest.mark.asyncio
async def test_provider_failure_skips_local_lookup() -> None:
    """Propagate dependency failure without attempting local admission."""
    reader = FixedPrincipalReader()
    with pytest.raises(DependencyUnavailableError):
        await HumanSessionAuthenticationService(
            FixedVerifier(failure=DependencyUnavailableError()),
            reader,
            recovery_block_reader=MockIdentityRecoveryBlockReader(),
        ).authenticate(CREDENTIAL)
    assert reader.identity is None


def test_credential_hides_secret_and_rejects_empty_value() -> None:
    """Prevent incidental disclosure and reject an absent credential at construction."""
    assert "synthetic-secret" not in repr(CREDENTIAL)
    with pytest.raises(ValueError):
        BrowserSessionCredential("")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_seconds", "total_seconds"),
    [(0.05, 1.0), (1.0, 0.05)],
)
async def test_cookie_provider_wait_uses_the_shorter_limit(
    provider_seconds: float,
    total_seconds: float,
) -> None:
    """A stuck Kratos check must respect both the provider cap and the total deadline."""
    verifier = MockDeadlineBrowserVerifier()
    verifier.blocked = True
    reader = MockDeadlinePrincipalReader()
    service = HumanSessionAuthenticationService(
        verifier,
        reader,
        recovery_block_reader=MockIdentityRecoveryBlockReader(),
        provider_timeout_seconds=provider_seconds,
        total_timeout_seconds=total_seconds,
    )

    # This guard makes missing deadline enforcement fail instead of hanging.
    async with asyncio.timeout(0.5):
        with pytest.raises(DependencyUnavailableError) as caught:
            await service.authenticate(CREDENTIAL)

    assert isinstance(caught.value.__cause__, TimeoutError)
    assert not reader.called


@pytest.mark.asyncio
async def test_cookie_total_deadline_includes_the_local_read() -> None:
    """Successful Kratos verification does not permit an unlimited database wait."""
    reader = MockDeadlinePrincipalReader()
    reader.blocked = True
    service = HumanSessionAuthenticationService(
        MockDeadlineBrowserVerifier(),
        reader,
        recovery_block_reader=MockIdentityRecoveryBlockReader(),
        total_timeout_seconds=0.05,
    )

    async with asyncio.timeout(0.5):
        with pytest.raises(DependencyUnavailableError) as caught:
            await service.authenticate(CREDENTIAL)

    assert reader.called
    assert isinstance(caught.value.__cause__, TimeoutError)


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", [IDENTITY, None])
async def test_cookie_late_provider_result_cannot_decide_authentication(
    identity: VerifiedHumanIdentityDTO | None,
) -> None:
    """An overdue provider result must produce 503, whether it accepts or rejects the cookie."""
    verifier = MockDeadlineBrowserVerifier()
    verifier.blocked = True
    verifier.return_after_cancellation = True
    verifier.result = identity
    reader = MockDeadlinePrincipalReader()
    service = HumanSessionAuthenticationService(
        verifier,
        reader,
        recovery_block_reader=MockIdentityRecoveryBlockReader(),
        provider_timeout_seconds=0.05,
    )

    async with asyncio.timeout(0.5):
        with pytest.raises(DependencyUnavailableError):
            await service.authenticate(CREDENTIAL)

    assert not reader.called


@pytest.mark.asyncio
@pytest.mark.parametrize("principal", [PRINCIPAL, None])
async def test_cookie_late_local_result_cannot_decide_admission(
    principal: Principal | None,
) -> None:
    """An overdue local result cannot admit a human or turn the timeout into a 403."""
    reader = MockDeadlinePrincipalReader()
    reader.blocked = True
    reader.return_after_cancellation = True
    reader.result = principal
    service = HumanSessionAuthenticationService(
        MockDeadlineBrowserVerifier(),
        reader,
        recovery_block_reader=MockIdentityRecoveryBlockReader(),
        total_timeout_seconds=0.05,
    )

    async with asyncio.timeout(0.5):
        with pytest.raises(DependencyUnavailableError):
            await service.authenticate(CREDENTIAL)


@pytest.mark.asyncio
async def test_external_cancellation_remains_cancellation() -> None:
    """A caller cancelling its request is different from verification timing out."""
    verifier = MockDeadlineBrowserVerifier()
    verifier.blocked = True
    reader = MockDeadlinePrincipalReader()
    service = HumanSessionAuthenticationService(
        verifier, reader, recovery_block_reader=MockIdentityRecoveryBlockReader()
    )

    task = asyncio.create_task(service.authenticate(CREDENTIAL))
    try:
        async with asyncio.timeout(0.5):
            await verifier.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    assert not reader.called


@pytest.mark.parametrize("setting", ["provider", "total"])
@pytest.mark.parametrize(
    "seconds",
    [True, 0.0, -1.0, float("nan"), float("inf"), float("-inf")],
)
def test_cookie_service_rejects_invalid_timeout_arguments(
    setting: Literal["provider", "total"],
    seconds: float,
) -> None:
    """Direct service construction must be safe even when settings parsing is bypassed."""
    with pytest.raises(ValueError, match="finite and positive"):
        HumanSessionAuthenticationService(
            MockDeadlineBrowserVerifier(),
            MockDeadlinePrincipalReader(),
            recovery_block_reader=MockIdentityRecoveryBlockReader(),
            provider_timeout_seconds=seconds if setting == "provider" else 5.0,
            total_timeout_seconds=seconds if setting == "total" else 10.0,
        )


@pytest.mark.asyncio
async def test_cookie_rechecks_recovery_without_clearing_suspension() -> None:
    """A released block restores eligibility only while the human remains active."""
    reader = FixedPrincipalReader()
    recovery = MockIdentityRecoveryBlockReader()
    service = HumanSessionAuthenticationService(
        FixedVerifier(), reader, recovery_block_reader=recovery
    )

    assert (await service.authenticate(CREDENTIAL)).actor_principal_id == PRINCIPAL.id

    recovery.result = True
    with pytest.raises(AccessDeniedError):
        await service.authenticate(CREDENTIAL)

    recovery.result = False
    assert (await service.authenticate(CREDENTIAL)).actor_principal_id == PRINCIPAL.id

    reader.principal = replace(PRINCIPAL, status=PrincipalStatus.SUSPENDED)
    with pytest.raises(AccessDeniedError):
        await service.authenticate(CREDENTIAL)

    assert recovery.identities == [IDENTITY] * 4


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [DependencyUnavailableError, TimeoutError, RuntimeError])
async def test_cookie_recovery_failure_preserves_its_category(
    failure_type: type[Exception],
) -> None:
    """Unavailable checks stop admission, while unexpected bugs remain visible."""
    recovery = MockIdentityRecoveryBlockReader()
    failure = failure_type()
    recovery.failure = failure
    service = HumanSessionAuthenticationService(
        FixedVerifier(), FixedPrincipalReader(), recovery_block_reader=recovery
    )
    expected = DependencyUnavailableError if failure_type is TimeoutError else failure_type

    with pytest.raises(expected) as caught:
        await service.authenticate(CREDENTIAL)

    if failure_type is TimeoutError:
        assert caught.value.__cause__ is failure
    else:
        assert caught.value is failure


@pytest.mark.asyncio
@pytest.mark.parametrize("return_after_cancellation", [False, True])
@pytest.mark.parametrize("result", [False, True])
async def test_cookie_total_deadline_includes_recovery_read(
    return_after_cancellation: bool, result: bool
) -> None:
    """An overdue check must not become a successful login or a recovery denial."""
    recovery = MockIdentityRecoveryBlockReader()
    recovery.stall = True
    recovery.return_after_cancellation = return_after_cancellation
    recovery.result = result
    service = HumanSessionAuthenticationService(
        FixedVerifier(),
        FixedPrincipalReader(),
        recovery_block_reader=recovery,
        total_timeout_seconds=0.02,
    )

    async with asyncio.timeout(1):
        with pytest.raises(DependencyUnavailableError) as caught:
            await service.authenticate(CREDENTIAL)

    assert isinstance(caught.value.__cause__, TimeoutError)
    assert recovery.identities == [IDENTITY]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["missing-credential", "provider", "local-link"])
async def test_cookie_rejection_before_admission_skips_recovery_read(
    stage: Literal["missing-credential", "provider", "local-link"],
) -> None:
    """Read recovery state only after a credential resolves to a local principal."""
    recovery = MockIdentityRecoveryBlockReader()
    service = HumanSessionAuthenticationService(
        FixedVerifier(None if stage == "provider" else IDENTITY),
        FixedPrincipalReader(None if stage == "local-link" else PRINCIPAL),
        recovery_block_reader=recovery,
    )
    expected = AccessDeniedError if stage == "local-link" else AuthenticationRequiredError

    with pytest.raises(expected):
        await service.authenticate(None if stage == "missing-credential" else CREDENTIAL)

    assert recovery.identities == []
