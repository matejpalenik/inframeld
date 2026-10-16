from typing import override

from sqlalchemy import exists, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_block_reader import (
    IdentityRecoveryBlockReader,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresIdentityRecoveryBlockReader(IdentityRecoveryBlockReader):
    """Read committed recovery blocks using authoritative installation metadata."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @override
    async def is_blocked(self, identity: VerifiedHumanIdentityDTO) -> bool:
        pending_block = (
            exists()
            .where(
                IdentityRecoveryAdmissionRow.installation_id
                == InstallationIdentityRow.installation_id,
                IdentityRecoveryAdmissionRow.authority == identity.authority.value,
                IdentityRecoveryAdmissionRow.subject == identity.subject.value,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .correlate(InstallationIdentityRow)
        )
        statement = (
            select(pending_block)
            .select_from(InstallationIdentityRow)
            .where(InstallationIdentityRow.singleton_key == 1)
        )

        try:
            async with self._database.session() as session:
                blocked = await session.scalar(statement)
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

        # No installation row must not look like a successful check with no block.
        if blocked is None:
            raise DependencyUnavailableError("The installation identity is not available.")

        return blocked
