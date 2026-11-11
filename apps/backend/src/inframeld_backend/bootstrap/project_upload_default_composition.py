from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.services.project_upload_default_fingerprint_service import (
    ProjectUploadDefaultFingerprintService,
)
from inframeld_backend.access.application.services.project_upload_default_service import (
    ProjectUploadDefaultService,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_upload_default_facts_reader import (
    PostgresProjectUploadDefaultFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_upload_default_repository import (
    PostgresProjectUploadDefaultRepository,
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
async def open_project_upload_default(
    database: Database, default_fingerprint_service: ProjectUploadDefaultFingerprintService
) -> AsyncGenerator[ProjectUploadDefaultService]:
    """Close one request-local session after the complete operation owns its transaction."""
    async with database.session() as session:
        yield ProjectUploadDefaultService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            default_facts_reader=PostgresProjectUploadDefaultFactsReader(session),
            default_repository=PostgresProjectUploadDefaultRepository(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            default_fingerprint_service=default_fingerprint_service,
        )
