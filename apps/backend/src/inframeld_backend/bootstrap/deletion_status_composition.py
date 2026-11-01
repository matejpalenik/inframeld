from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.services.deletion_status_authorization_service import (
    DeletionStatusAuthorizationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_deletion_status_facts_reader import (
    PostgresDeletionStatusFactsReader,
)
from inframeld_backend.shared.application.protocols.deletion_status_lookup import (
    DeletionStatusLookup,
)
from inframeld_backend.shared.application.services.deletion_status_read_service import (
    DeletionStatusReadService,
)
from inframeld_backend.shared.infrastructure.readers.postgres_deletion_status_reader import (
    PostgresDeletionStatusReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


@asynccontextmanager
async def open_deletion_status_lookup(database: Database) -> AsyncGenerator[DeletionStatusLookup]:
    """Hold current eligibility coordination through projection, then close the read transaction."""
    async with database.session() as session, session.begin():
        yield DeletionStatusReadService(
            DeletionStatusAuthorizationService(PostgresDeletionStatusFactsReader(session)),
            PostgresDeletionStatusReader(session),
        )
