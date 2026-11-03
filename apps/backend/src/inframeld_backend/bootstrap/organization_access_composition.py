from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.my_organization_access_reader import (
    MyOrganizationAccessReader,
)
from inframeld_backend.access.application.services.my_organization_access_service import (
    MyOrganizationAccessService,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_access_facts_reader import (
    PostgresOrganizationAccessFactsReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


@asynccontextmanager
async def open_my_organization_access(
    database: Database,
) -> AsyncGenerator[MyOrganizationAccessReader]:
    async with database.session() as session:
        yield MyOrganizationAccessService(PostgresOrganizationAccessFactsReader(session))
