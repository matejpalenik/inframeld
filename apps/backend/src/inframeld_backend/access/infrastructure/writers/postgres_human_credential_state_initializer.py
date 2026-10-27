import asyncio
from typing import override

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_credential_state_initializer import (
    HumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.mappers.postgres_human_credential_state_mapper import (
    PostgresHumanCredentialStateMapper,
)
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresHumanCredentialStateInitializer(HumanCredentialStateInitializer):
    """Finish metadata initialization in a short transaction before provider verification."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @override
    async def initialize(self, identity: VerifiedHumanIdentityDTO) -> HumanCredentialStateDTO:
        try:
            async with asyncio.timeout(5.0), self._database.session() as session, session.begin():
                installation = await session.scalar(
                    select(InstallationIdentityRow.installation_id).where(
                        InstallationIdentityRow.singleton_key == 1
                    )
                )
                if installation is None:
                    raise DependencyUnavailableError("The installation identity is not available.")
                await PostgresIdentityCoordinator(session).acquire(
                    installation_id=InstallationId(installation), identity=identity
                )
                statement = HumanCredentialStateQueries.for_identity(identity)
                result = await session.execute(statement)
                row = result.tuples().one_or_none()
                state = PostgresHumanCredentialStateMapper.to_state(identity, row)
                if state.installation_id.value != installation:
                    raise DependencyUnavailableError("The installation identity is not available.")
                if state.version is None:
                    if row is not None and row[3]:
                        raise DependencyUnavailableError(
                            "Credential history requires its original version state."
                        )
                    await session.execute(
                        insert(HumanCredentialVersionRow)
                        .values(
                            installation_id=state.installation_id.value,
                            authority=identity.authority.value,
                            subject=identity.subject.value,
                            version=1,
                        )
                        .on_conflict_do_nothing()
                    )
                    result = await session.execute(statement)
                    state = PostgresHumanCredentialStateMapper.to_state(
                        identity, result.tuples().one_or_none()
                    )
                return state
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
