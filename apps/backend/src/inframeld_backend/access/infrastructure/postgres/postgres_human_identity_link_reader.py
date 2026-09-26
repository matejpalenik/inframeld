"""Load linked principal state through an independent, short PostgreSQL read session."""

from typing import override

from sqlalchemy import select

from inframeld_backend.access.application.authentication.human_identity_link_reader import (
    HumanIdentityLinkReader,
)
from inframeld_backend.access.application.authentication.verified_human_identity import (
    VerifiedHumanIdentity,
)
from inframeld_backend.access.domain.organization_values import OrganizationId
from inframeld_backend.access.domain.principal import Principal, PrincipalId
from inframeld_backend.access.infrastructure.postgres.models.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.postgres.models.principal_row import PrincipalRow
from inframeld_backend.shared.infrastructure.postgres.database import Database


class PostgresHumanIdentityLinkReader(HumanIdentityLinkReader):
    """Load the local principal linked to an exact verified identity pair.

    Each lookup owns a fresh read session, so this adapter can be shared across
    requests. It returns detached domain state; the service decides admission.
    """

    def __init__(self, database: Database) -> None:
        """Retain the session factory owner; no session is opened or shared at construction."""
        self._database = database

    @override
    async def find_principal(self, identity: VerifiedHumanIdentity) -> Principal | None:
        """Join the exact stored identity pair to its principal and detach typed domain state."""
        statement = (
            select(PrincipalRow)
            .join(HumanIdentityLinkRow, HumanIdentityLinkRow.principal_id == PrincipalRow.id)
            .where(
                HumanIdentityLinkRow.authority == identity.authority.value,
                HumanIdentityLinkRow.subject == identity.subject.value,
            )
        )
        async with self._database.session() as session:
            row = await session.scalar(statement)
            if row is None:
                return None
            return Principal(
                id=PrincipalId(row.id),
                organization_id=OrganizationId(row.organization_id),
                kind=row.kind,
                status=row.status,
            )
