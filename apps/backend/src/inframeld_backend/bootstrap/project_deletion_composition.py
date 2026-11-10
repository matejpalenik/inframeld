from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.project_deleter import ProjectDeleter
from inframeld_backend.access.application.services.project_deletion_fingerprint_service import (
    ProjectDeletionFingerprintService,
)
from inframeld_backend.access.application.services.project_deletion_service import (
    ProjectDeletionService,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_deletion_facts_reader import (
    PostgresProjectDeletionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_deletion_result_reader import (
    PostgresProjectDeletionResultReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_deletion_admission_writer import (
    PostgresProjectDeletionAdmissionWriter,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


@asynccontextmanager
async def open_project_deletion(
    database: Database,
    fingerprints: RequestFingerprintService,
    retention_profile: DeletionStatusRetentionProfile,
) -> AsyncGenerator[ProjectDeleter]:
    """Close one request-local session after the service's original bounded transaction."""
    async with database.session() as session:
        yield ProjectDeletionService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            project_deletion_facts_reader=PostgresProjectDeletionFactsReader(session),
            project_deletion_admission_writer=PostgresProjectDeletionAdmissionWriter(
                session, retention_profile=retention_profile
            ),
            project_deletion_result_reader=PostgresProjectDeletionResultReader(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            project_deletion_fingerprint_service=ProjectDeletionFingerprintService(fingerprints),
        )
