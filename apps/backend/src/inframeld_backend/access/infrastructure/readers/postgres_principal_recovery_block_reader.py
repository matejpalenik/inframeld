from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresPrincipalRecoveryBlockReader:
    """Read recovery state using the caller's transaction and stored identity links.

    The caller owns the session and any write locks. Confirmed provider outcomes
    still require explicit release of the block.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_blocked(self, principal_id: PrincipalId) -> bool:
        pending_block = (
            select(IdentityRecoveryAdmissionRow.operation_id)
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanIdentityLinkRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .where(
                IdentityRecoveryAdmissionRow.installation_id
                == InstallationIdentityRow.installation_id,
                HumanIdentityLinkRow.principal_id == principal_id.value,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .exists()
            .correlate(InstallationIdentityRow)
        )

        statement = (
            select(pending_block)
            .select_from(InstallationIdentityRow)
            .where(InstallationIdentityRow.singleton_key == 1)
        )

        blocked = await self._session.scalar(statement)
        if blocked is None:
            raise DependencyUnavailableError("The installation identity is not available.")

        return blocked
