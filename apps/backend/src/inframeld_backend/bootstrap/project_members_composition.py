from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.project_members_reader import (
    ProjectMembersReader,
)
from inframeld_backend.access.application.services.project_members_service import (
    ProjectMembersService,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_members_facts_reader import (
    PostgresProjectMembersFactsReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


@asynccontextmanager
async def open_project_members(database: Database) -> AsyncGenerator[ProjectMembersReader]:
    """Close the read-only request session after its one bounded observation."""
    async with database.session() as session:
        yield ProjectMembersService(PostgresProjectMembersFactsReader(session))
