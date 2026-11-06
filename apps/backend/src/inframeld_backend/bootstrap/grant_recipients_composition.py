from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.project_grant_recipients_reader import (
    ProjectGrantRecipientsReader,
)
from inframeld_backend.access.application.services.project_grant_recipients_service import (
    ProjectGrantRecipientsService,
)
from inframeld_backend.access.infrastructure.readers.postgres_grant_recipients_facts_reader import (
    PostgresGrantRecipientsFactsReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


@asynccontextmanager
async def open_project_grant_recipients(
    database: Database,
) -> AsyncGenerator[ProjectGrantRecipientsReader]:
    """Close one clean read session after a bounded current-authority directory page."""
    async with database.session() as session:
        yield ProjectGrantRecipientsService(
            grant_recipients_facts_reader=PostgresGrantRecipientsFactsReader(session)
        )
