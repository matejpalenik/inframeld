from sqlalchemy import select

from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.errors.installation_identity_error import (
    InstallationIdentityError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresInstallationIdentityReader:
    """Read authoritative installation metadata through a short, independent session."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def read(self) -> InstallationId:
        """Return the original identity, failing rather than generating a replacement."""
        statement = select(InstallationIdentityRow.installation_id).where(
            InstallationIdentityRow.singleton_key == 1
        )
        async with self._database.session() as session:
            installation_id = await session.scalar(statement)

        if installation_id is None:
            raise InstallationIdentityError("The installation identity is missing.")

        return InstallationId(installation_id)
