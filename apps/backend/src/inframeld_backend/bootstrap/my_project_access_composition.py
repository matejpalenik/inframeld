from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.my_project_access_reader import (
    MyProjectAccessReader,
)
from inframeld_backend.access.application.services.my_project_access_service import (
    MyProjectAccessService,
)
from inframeld_backend.access.infrastructure.readers.postgres_my_project_access_facts_reader import (
    PostgresMyProjectAccessFactsReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


@asynccontextmanager
async def open_my_project_access(database: Database) -> AsyncGenerator[MyProjectAccessReader]:
    """Close one clean read session after the bounded own-access operation."""
    async with database.session() as session:
        yield MyProjectAccessService(PostgresMyProjectAccessFactsReader(session))
