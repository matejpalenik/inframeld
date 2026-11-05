from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.project_name_resolver import ProjectNameResolver
from inframeld_backend.access.application.services.project_metadata_authorization_service import (
    ProjectMetadataAuthorizationService,
)
from inframeld_backend.access.application.services.project_metadata_fingerprint_service import (
    ProjectMetadataFingerprintService,
)
from inframeld_backend.access.application.services.project_metadata_service import (
    ProjectMetadataService,
)
from inframeld_backend.access.application.services.project_name_resolution_service import (
    ProjectNameResolutionService,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_metadata_facts_reader import (
    PostgresProjectMetadataFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_name_binding_reader import (
    PostgresProjectNameBindingReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_metadata_repository import (
    PostgresProjectMetadataRepository,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_metadata_audit_writer import (
    PostgresProjectMetadataAuditWriter,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.resource_name_resolution_service import (
    ResourceNameResolutionService,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


@asynccontextmanager
async def open_project_metadata(
    database: Database, metadata_fingerprint_service: ProjectMetadataFingerprintService
) -> AsyncGenerator[ProjectMetadataService]:
    async with database.session() as session:
        yield ProjectMetadataService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            metadata_authorizer=ProjectMetadataAuthorizationService(
                PostgresProjectMetadataFactsReader(session)
            ),
            metadata_repository=PostgresProjectMetadataRepository(
                session, PostgresProjectMetadataAuditWriter(session)
            ),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            metadata_fingerprint_service=metadata_fingerprint_service,
        )


@asynccontextmanager
async def open_project_name_resolution(database: Database) -> AsyncGenerator[ProjectNameResolver]:
    async with database.session() as session:
        facts = PostgresProjectMetadataFactsReader(session)
        yield ProjectNameResolutionService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            metadata_facts_reader=facts,
            resource_name_resolver=ResourceNameResolutionService(
                PostgresProjectNameBindingReader(session)
            ),
            metadata_authorizer=ProjectMetadataAuthorizationService(facts),
            metadata_repository=PostgresProjectMetadataRepository(
                session, PostgresProjectMetadataAuditWriter(session)
            ),
        )
