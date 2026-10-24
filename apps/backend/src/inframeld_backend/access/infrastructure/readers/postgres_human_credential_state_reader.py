import asyncio
from typing import override

from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_credential_state_reader import (
    HumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.mappers.postgres_human_credential_state_mapper import (
    PostgresHumanCredentialStateMapper,
)
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


class PostgresHumanCredentialStateReader(HumanCredentialStateReader):
    """Read one committed projection in an independent session with a five-second deadline."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @override
    async def read(self, identity: VerifiedHumanIdentityDTO) -> HumanCredentialStateDTO:
        try:
            async with asyncio.timeout(5.0), self._database.session() as session:
                result = await session.execute(HumanCredentialStateQueries.for_identity(identity))
                return PostgresHumanCredentialStateMapper.to_state(
                    identity, result.tuples().one_or_none()
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
