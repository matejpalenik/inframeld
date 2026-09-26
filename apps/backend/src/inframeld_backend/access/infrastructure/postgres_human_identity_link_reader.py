"""Read verified human identity links from PostgreSQL"""

from typing import final

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.human_session import (
    HumanIdentityLinkReader,
    VerifiedHumanIdentity,
)
from inframeld_backend.access.domain.values import PrincipalId, PrincipalKind, PrincipalStatus
from inframeld_backend.access.infrastructure.persistence_models import (
    HumanIdentityLinkRow,
    PrincipalRow,
)


@final
class PostgresHumanIdentityLinkReader(HumanIdentityLinkReader):
    """Read an active human principal using an existing database session"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_active_principal_id(self, identity: VerifiedHumanIdentity) -> PrincipalId | None:

        statement = (
            select(PrincipalRow.id)
            .select_from(HumanIdentityLinkRow)
            .join(
                PrincipalRow,
                and_(
                    PrincipalRow.id == HumanIdentityLinkRow.principal_id,
                    PrincipalRow.organization_id == HumanIdentityLinkRow.organization_id,
                    PrincipalRow.kind == HumanIdentityLinkRow.principal_kind,
                ),
            )
            .where(
                HumanIdentityLinkRow.authority == identity.authority.value,
                HumanIdentityLinkRow.subject == identity.subject.value,
                PrincipalRow.kind == PrincipalKind.HUMAN,
                PrincipalRow.status == PrincipalStatus.ACTIVE,
            )
        )

        principal_id = await self._session.scalar(statement)
        return PrincipalId(principal_id) if principal_id is not None else None
