"""Load linked principal state through an independent, short PostgreSQL read session."""

from typing import override

from sqlalchemy import select

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_identity_link_reader import (
    HumanIdentityLinkReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.infrastructure.resources.database import Database


class PostgresHumanIdentityLinkReader(HumanIdentityLinkReader):
    """Load the local principal linked to an exact verified identity pair.

    Each lookup owns a fresh read session, so this adapter can be shared across
    requests. It returns detached domain state; the service decides admission.
    """

    def __init__(self, database: Database) -> None:
        """Retain the session factory owner; no session is opened or shared at construction."""
        self._database = database

    @override
    async def find_principal(self, identity: VerifiedHumanIdentityDTO) -> Principal | None:
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
