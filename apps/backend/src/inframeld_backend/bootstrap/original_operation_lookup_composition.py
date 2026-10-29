from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.services.operation_lookup_authorization_service import (
    OperationLookupAuthorizationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_operation_lookup_facts_reader import (
    PostgresOperationLookupFactsReader,
)
from inframeld_backend.shared.application.protocols.original_operation_lookup import (
    OriginalOperationLookup,
)
from inframeld_backend.shared.application.services.original_operation_lookup_service import (
    OriginalOperationLookupService,
)
from inframeld_backend.shared.infrastructure.readers.postgres_operation_lookup_reader import (
    PostgresOperationLookupReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


@asynccontextmanager
async def open_original_operation_lookup(
    database: Database,
) -> AsyncGenerator[OriginalOperationLookup]:
    """Close one request-local read session after current authority and original lookup."""
    async with database.session() as session:
        yield OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        )
