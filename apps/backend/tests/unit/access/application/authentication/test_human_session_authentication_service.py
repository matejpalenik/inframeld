"""Verify provider authentication and local admission as one application workflow."""

from dataclasses import replace
from typing import override
from uuid import uuid4

import pytest

from inframeld_backend.access.application.authentication.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.authentication.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.authentication.human_identity_link_reader import (
    HumanIdentityLinkReader,
)
from inframeld_backend.access.application.authentication.human_session_authentication_service import (
    HumanSessionAuthenticationService,
)
from inframeld_backend.access.application.authentication.verified_human_identity import (
    VerifiedHumanIdentity,
)
from inframeld_backend.access.domain.identity_values import IdentityAuthority, IdentitySubject
from inframeld_backend.access.domain.organization_values import OrganizationId
from inframeld_backend.access.domain.principal import (
    Principal,
    PrincipalId,
    PrincipalKind,
    PrincipalStatus,
)
from inframeld_backend.shared.application.errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)

IDENTITY = VerifiedHumanIdentity(IdentityAuthority("kratos:test"), IdentitySubject("alice"))
PRINCIPAL = Principal(
    PrincipalId(uuid4()), OrganizationId(uuid4()), PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
CREDENTIAL = BrowserSessionCredential("synthetic-secret")


class FixedVerifier(BrowserSessionVerifier):
    """Return a provider outcome and record whether verification was attempted."""

    def __init__(
        self, identity: VerifiedHumanIdentity | None = IDENTITY, failure: Exception | None = None
    ) -> None:
        """Choose the provider result used by an authentication scenario."""
        self.identity = identity
        self.failure = failure
        self.called = False

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentity | None:
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
        self.identity: VerifiedHumanIdentity | None = None

    @override
    async def find_principal(self, identity: VerifiedHumanIdentity) -> Principal | None:
        """Return current local state for the identity supplied by verification."""
        self.identity = identity
        return self.principal


@pytest.mark.asyncio
async def test_valid_identity_resolves_active_local_human() -> None:
    """Carry the verified identity into lookup and return only the local principal ID."""
    reader = FixedPrincipalReader()
    context = await HumanSessionAuthenticationService(FixedVerifier(), reader).authenticate(
        CREDENTIAL
    )
    assert context.actor_principal_id == PRINCIPAL.id
    assert reader.identity == IDENTITY


@pytest.mark.asyncio
async def test_missing_credential_performs_no_io() -> None:
    """Reject a missing session before contacting either external dependency."""
    verifier, reader = FixedVerifier(), FixedPrincipalReader()
    with pytest.raises(AuthenticationRequiredError):
        await HumanSessionAuthenticationService(verifier, reader).authenticate(None)
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
            FixedVerifier(), FixedPrincipalReader(principal)
        ).authenticate(CREDENTIAL)


@pytest.mark.asyncio
async def test_rejected_session_skips_local_lookup() -> None:
    """Require successful provider verification before reading local principal state."""
    reader = FixedPrincipalReader()
    with pytest.raises(AuthenticationRequiredError):
        await HumanSessionAuthenticationService(FixedVerifier(None), reader).authenticate(
            CREDENTIAL
        )
    assert reader.identity is None


@pytest.mark.asyncio
async def test_provider_failure_skips_local_lookup() -> None:
    """Propagate dependency failure without attempting local admission."""
    reader = FixedPrincipalReader()
    with pytest.raises(DependencyUnavailableError):
        await HumanSessionAuthenticationService(
            FixedVerifier(failure=DependencyUnavailableError()), reader
        ).authenticate(CREDENTIAL)
    assert reader.identity is None


def test_credential_hides_secret_and_rejects_empty_value() -> None:
    """Prevent incidental disclosure and reject an absent credential at construction."""
    assert "synthetic-secret" not in repr(CREDENTIAL)
    with pytest.raises(ValueError):
        BrowserSessionCredential("")
