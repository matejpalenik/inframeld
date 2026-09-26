"""Verify exact identity lookup, fresh account state, and concurrent authentication."""

import asyncio
import os
from typing import override
from uuid import uuid4

import pytest
from sqlalchemy import update
from tests.support.access_scenarios import seed_linked_human

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.services.human_session_authentication_service import (
    HumanSessionAuthenticationService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_human_identity_link_reader import (
    PostgresHumanIdentityLinkReader,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Set INFRAMELD_RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests",
)
AUTHORITY = IdentityAuthority("kratos:test")


class CredentialSubjectVerifier(BrowserSessionVerifier):
    """Use synthetic credentials as subjects to exercise local persistence concurrently."""

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        """Return the exact test identity represented by this synthetic credential."""
        return VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(credential.value))


@pytest.mark.asyncio
@pytest.mark.parametrize("status", list(PrincipalStatus))
async def test_exact_identity_link_returns_principal_state(
    database: Database, status: PrincipalStatus
) -> None:
    """Return linked state without applying the application's active-human policy in SQL."""
    identity = VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(str(uuid4())))
    async with database.session() as session, session.begin():
        seeded = await seed_linked_human(session, identity, status=status)
    principal = await PostgresHumanIdentityLinkReader(database).find_principal(identity)
    assert principal is not None
    assert principal.id == seeded.id
    assert principal.organization_id == seeded.organization_id
    assert principal.kind is seeded.kind
    assert principal.status is status


@pytest.mark.asyncio
@pytest.mark.parametrize("change_authority", [True, False])
async def test_identity_lookup_requires_both_exact_values(
    database: Database, change_authority: bool
) -> None:
    """Reject near matches when either verified authority or subject differs."""
    identity = VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject("Alice "))
    async with database.session() as session, session.begin():
        await seed_linked_human(session, identity)
    mismatch = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:Test") if change_authority else identity.authority,
        identity.subject if change_authority else IdentitySubject("Alice"),
    )
    assert await PostgresHumanIdentityLinkReader(database).find_principal(mismatch) is None


@pytest.mark.asyncio
async def test_shared_service_authenticates_concurrent_callers(database: Database) -> None:
    """Keep each overlapping caller's read session and principal result independent."""
    identities = [
        VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(str(uuid4()))) for _ in range(12)
    ]
    async with database.session() as session, session.begin():
        principals = [await seed_linked_human(session, identity) for identity in identities]
    service = HumanSessionAuthenticationService(
        CredentialSubjectVerifier(), PostgresHumanIdentityLinkReader(database)
    )
    contexts = await asyncio.gather(
        *(
            service.authenticate(BrowserSessionCredential(identity.subject.value))
            for identity in identities
        )
    )
    assert [context.actor_principal_id for context in contexts] == [
        principal.id for principal in principals
    ]


@pytest.mark.asyncio
async def test_shared_service_reads_account_status_on_each_request(database: Database) -> None:
    """Deny the next authentication after a principal is suspended by another transaction."""
    identity = VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(str(uuid4())))
    async with database.session() as session, session.begin():
        principal = await seed_linked_human(session, identity)
    service = HumanSessionAuthenticationService(
        CredentialSubjectVerifier(), PostgresHumanIdentityLinkReader(database)
    )
    credential = BrowserSessionCredential(identity.subject.value)
    assert (await service.authenticate(credential)).actor_principal_id == principal.id
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == principal.id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
    with pytest.raises(AccessDeniedError):
        await service.authenticate(credential)
