from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.project_creator import ProjectCreator
from inframeld_backend.access.application.services.project_creation_authorization_service import (
    ProjectCreationAuthorizationService,
)
from inframeld_backend.access.application.services.project_creation_fingerprint_service import (
    ProjectCreationFingerprintService,
)
from inframeld_backend.access.application.services.project_creation_service import (
    ProjectCreationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_access_facts_reader import (
    PostgresOrganizationAccessFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_creation_result_reader import (
    PostgresProjectCreationResultReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_creation_writer import (
    PostgresProjectCreationWriter,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


@asynccontextmanager
async def open_project_creation(
    database: Database, fingerprints: ProjectCreationFingerprintService
) -> AsyncGenerator[ProjectCreator]:
    async with database.session() as session:
        yield ProjectCreationService(
            transactions=SqlAlchemyTransactionManager(session),
            authorizer=ProjectCreationAuthorizationService(
                PostgresOrganizationAccessFactsReader(session)
            ),
            writer=PostgresProjectCreationWriter(session),
            results=PostgresProjectCreationResultReader(session),
            idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            fingerprints=fingerprints,
        )
