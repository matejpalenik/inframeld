"""Verify that a stored human identity resolves to its active local principal."""

import os
from uuid import uuid4

import pytest

from inframeld_backend.access.application.access_authorizer import AccessContext
from inframeld_backend.access.application.human_session import (
    HumanSessionResolver,
    VerifiedHumanIdentity,
)
from inframeld_backend.access.domain.values import (
    IdentityAuthority,
    IdentitySubject,
    OrganizationId,
    PrincipalId,
    PrincipalKind,
    PrincipalStatus,
)
from inframeld_backend.access.infrastructure.persistence_models import (
    HumanIdentityLinkRow,
    OrganizationRow,
    PrincipalRow,
)
from inframeld_backend.access.infrastructure.postgres_human_identity_link_reader import (
    PostgresHumanIdentityLinkReader,
)
from inframeld_backend.shared.infrastructure.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Set INFRAMELD_RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests",
)


@pytest.mark.asyncio
async def test_exact_identity_link_resolves_active_human(database: Database) -> None:
    """Return the linked principal for an exact verified authority and subject."""
    organization_id = OrganizationId(uuid4())
    principal_id = PrincipalId(uuid4())
    authority = IdentityAuthority("kratos:local")
    subject = IdentitySubject("alice-kratos-id")

    async with database.session() as session, session.begin():
        session.add(OrganizationRow(id=organization_id, name="Test organization"))
        await session.flush()
        session.add(
            PrincipalRow(
                id=principal_id,
                organization_id=organization_id,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Alice",
            )
        )
        await session.flush()
        session.add(
            HumanIdentityLinkRow(
                authority=authority.value,
                subject=subject.value,
                organization_id=organization_id,
                principal_id=principal_id,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        await session.flush()

        resolver = HumanSessionResolver(PostgresHumanIdentityLinkReader(session))
        access = await resolver.resolve(
            VerifiedHumanIdentity(
                authority=authority,
                subject=subject,
            )
        )

    assert access == AccessContext(actor_principal_id=principal_id)
