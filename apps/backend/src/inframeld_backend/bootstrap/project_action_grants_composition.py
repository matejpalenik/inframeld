from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.project_action_grants_reader import (
    ProjectActionGrantsReader,
)
from inframeld_backend.access.application.services.project_action_grants_service import (
    ProjectActionGrantsService,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_grants_facts_reader import (
    PostgresProjectActionGrantsFactsReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


@asynccontextmanager
async def open_project_action_grants(
    database: Database,
) -> AsyncGenerator[ProjectActionGrantsReader]:
    """Close one clean read session without granting authority or committing writes."""
    async with database.session() as session:
        yield ProjectActionGrantsService(PostgresProjectActionGrantsFactsReader(session))
